#!/usr/bin/env python

__doc__ = """
Pure Python alternative to readline and cmm.Cmd.

Author: Jonathan Slenders
"""

import logging
import os
import termcolor
import termios
import time
import traceback

from twisted.internet import fdesc
from deployer.pseudo_terminal import select
from deployer.std import raw_mode
from deployer.console import Console

from pygments import highlight
from pygments.lexers import PythonTracebackLexer
from pygments.formatters import TerminalFormatter


def commonprefix(*strings):
    # Similar to os.path.commonprefix
    if not strings:
        return ''

    else:
        s1 = min(strings)
        s2 = max(strings)

        for i, c in enumerate(s1):
            if c != s2[i]:
                return s1[:i]

        return s1


class ExitCLILoop(Exception):
    def __init__(self, result=None):
        self.result = result


class CLInterface(object):
    """
    A pure-python implementation of a command line completion interface.
    It does not rely on readline or raw_input, which don't offer
    autocompletion in Python 2.6/2.7 when different ptys are used in different
    threads.
    """
    not_found_message = 'Command not found...'
    not_a_leaf_message = 'Incomplete command...'

    @property
    def prompt(self):
        return [ ('>', 'cyan') ]

    def __init__(self, pty, rootHandler):
        self.pty = pty
        self.stdin = pty.stdin
        self.stdout = pty.stdout
        self.root = rootHandler
        self.lines_history = []
        self.history_position = 0 # 0 is behind the history, -1 is browsing one backwards

        self.tcattr = termios.tcgetattr(self.stdin.fileno())
        self.line = [] # Character array
        self.insert_pos = 0
        self.scroll_pos = 0 # Horizontal scrolling
        self.vi_navigation = False # In vi-navigation mode (instead of insert mode.)

        # Additional pipe through which this shell can receive messages while
        # waiting for IO.
        r, w = os.pipe()
        self._extra_stdout = os.fdopen(w, 'w', 0)
        self._extra_stdin = os.fdopen(r, 'r', 0)
        fdesc.setNonBlocking(self._extra_stdin)

        self.currently_running = None

    def __del__(self):
        self._extra_stdout.close()
        self._extra_stdin.close()

    def write(self, data):
        self._extra_stdout.write(data)

    def completer(self, parts, lastPart):
        """
        Return a list of (name, handler)
        matching the last completion part.
        """
        h = self.root
        parts = parts[:]

        while h and parts:# and not h.is_leaf:
            try:
                h = h.get_subhandler(parts[0])
                parts = parts[1:]
            except NoSubHandler, e:
                return []

        if h and not parts:
            return list(h.complete_subhandlers(lastPart))
        else:
            return []

    def handle(self, parts):
        original_parts = parts
        h = self.root
        parts = parts[:]

        logging.info('Handle command line action "%s"' % ' '.join(parts))

        while h and parts:# and not h.is_leaf:
            try:
                h = h.get_subhandler(parts[0])
            except (NotImplementedError, NoSubHandler):
                print 'Not implemented...'
                return

            parts = parts[1:]

        if h and not parts:
            if h.is_leaf:
                self.currently_running = ' '.join(original_parts)
                try:
                    h()
                except ExitCLILoop:
                    raise
                except Exception as e:
                    self.handle_exception(e)
                self.currently_running = None
            else:
                print self.not_a_leaf_message
        else:
            print self.not_found_message

    def handle_exception(self, e):
        """
        Default exception handler when something went wrong in the shell.
        """
        tb = traceback.format_exc()
        print highlight(tb, PythonTracebackLexer(), TerminalFormatter())
        print e

    def complete(self, return_all_completions=False):
        # Take part before cursor
        l = ''.join(self.line)[:self.insert_pos]

        # Split parts
        parts = [ p for p in l.split() if p ] or [ '' ]

        # When there's a space below the cursor, it means that we are
        # at the start of a new part.
        if self.insert_pos > 0 and self.line[self.insert_pos - 1].isspace():
            parts.append('')

        possible_completions = self.completer(parts[:-1], parts[-1])

        if return_all_completions:
            return possible_completions
        else:
            last_part_len = len(parts[-1])
            possible_completions = [ c[0] for c in possible_completions ]
            if len(possible_completions) == 1:
                # When exactly one match, append a space
                return possible_completions[0][last_part_len:] + ' '
            else:
                return commonprefix(*possible_completions)[last_part_len:]

    def print_all_completions(self, all_completions):
        self.stdout.write('\r\n')

        # Create an iterator which yields all the comments (in their color),
        # and pass it through in_columns/lesspipe
        def column_items():
            for w in all_completions:
                handler_type = w[1].handler_type
                text = '%s%s' % (
                    termcolor.colored(w[0], handler_type.color),
                    termcolor.colored(handler_type.postfix, handler_type.postfix_color))
                length = len(w[0]) + len(handler_type.postfix)
                yield text, length

        c = Console(self.pty)
        c.lesspipe(c.in_columns(column_items()))

    def ctrl_c(self):
        # Initialize new read
        self.line = []
        self.insert_pos = 0
        self.history_position = 0
        self.vi_navigation = False

        # Print promt again
        self.stdout.write('\r\n')
        self.print_command()


    def print_command(self, only_if_scrolled=False):
        """
        Print the whole command line prompt.
        """
        termwidth = self.pty.get_width()
        prompt_out, prompt_length = self._make_prompt(termwidth)

        changed = self._update_scroll(prompt_length)
        if changed or not only_if_scrolled:
            self._print_command(prompt_out, prompt_length, termwidth)

    def _make_prompt(self, termwidth):
        """
        Create a (outbuffer, promptsize) object.
        """
        out = []
        pos = 0

        # Call prompt property
        prompt = self.prompt

        # Max prompt size
        max_prompt_size = termwidth / 2

        # Loop backwards over all the parts, truncate when required.
        while prompt and pos < max_prompt_size:
            text, color = prompt.pop()

            if len(text) > max_prompt_size - pos:
                text = text[-(max_prompt_size-pos):]

            out = [ termcolor.colored(text, color) ] + out
            pos += len(text)

        return out, pos

    def _update_scroll(self, prompt_length):
        """
        Update scroll, to make sure that the cursor is always visible.
        """
        changed = False

        # Make sure that the cursor is within range.
        # (minus one, because we need to have an insert prompt available after the input text.)
        available_width = self.pty.get_width() - prompt_length - 1

        # Make sure that the insert position is visible
        if self.insert_pos > available_width + self.scroll_pos:
            self.scroll_pos = self.insert_pos - available_width
            changed = True

        if self.insert_pos < self.scroll_pos:
            self.scroll_pos = self.insert_pos
            changed = True

        # Make sure that the scrolling pos is never larger than it has to be.
        # e.g. after enlarging the window size.
        if self.scroll_pos > len(self.line) - available_width:
            self.scroll_pos = max(0, len(self.line) - available_width)

        return changed

    def _print_command(self, prompt_out, prompt_length, termwidth):
        """
        Reprint prompt.
        """
        # We have an unbufferred stdout, so it's faster to write only once.
        out = [ ]

        # Move cursor position to the left.
        out.append('\x1b[%iD' % termwidth)

        # Erace until the end of line
        out.append('\x1b[K')

        # Add prompt
        pos = prompt_length
        out += prompt_out

        # Horizontal scrolling
        scroll_pos = self.scroll_pos

        # Print interactive part of command line
        line = ''.join(self.line)
        h = self.root

        while line:
            if line[0].isspace():
                overflow = pos+1 > termwidth
                if overflow:
                    break
                else:
                    if scroll_pos:
                        scroll_pos -= 1
                    else:
                        out.append(line[0])
                        pos += 1

                line = line[1:]
            else:
                # First following part
                p = line.split()[0]
                line = line[len(p):]

                # Get color
                color = None
                if h:
                    try:
                        h = h.get_subhandler(p)
                        if h:
                            color = h.handler_type.color
                    except (NotImplementedError, NoSubHandler):
                        pass

                while scroll_pos and p:
                    scroll_pos -= 1
                    p = p[1:]

                # Trim when the line's too long.
                overflow = pos + len(p) > termwidth
                if overflow:
                    p = p[:termwidth-pos]

                # Print this slice in the correct color.
                out.append(termcolor.colored(p, color))
                pos += len(p)

                if overflow:
                    break

        # Move cursor to correct position
        out.append('\x1b[%iD' % termwidth) # Move 'x' positions backwards (to the start of the line)
        out.append('\x1b[%iC' % (prompt_length + self.insert_pos - self.scroll_pos)) # Move back to right

        # Flush buffer
        self.stdout.write(''.join(out))
        self.stdout.flush()

    def clear(self):
        # Erase screen and move cursor to 0,0
        self.stdout.write('\033[2J\033[0;0H')
        self.print_command()

    def backspace(self):
        if self.insert_pos > 0:
            self.line = self.line[:self.insert_pos-1] + self.line[self.insert_pos:]
            self.insert_pos -= 1

            self.print_command()
        else:
            self.stdout.write('\a') # Beep

    def cursor_left(self):
        if self.insert_pos > 0:
            self.insert_pos -= 1
            self.stdout.write('\x1b[D') # Move to left

            self.print_command(True)

    def cursor_right(self):
        if self.insert_pos < len(self.line):
            self.insert_pos += 1
            self.stdout.write('\x1b[C') # Move to right

            self.print_command(True)

    def word_forwards(self):
        found_space = False
        while self.insert_pos < len(self.line) - 1:
            self.insert_pos += 1
            self.stdout.write('\x1b[C') # Move to right

            if self.line[self.insert_pos].isspace():
                found_space = True
            elif found_space:
                return

        self.print_command(True)

    def word_backwards(self):
        found_non_space = False
        while self.insert_pos > 0:
            self.insert_pos -= 1
            self.stdout.write('\x1b[D') # Move to left

            if not self.line[self.insert_pos].isspace():
                found_non_space = True
            if found_non_space and self.insert_pos > 0 and self.line[self.insert_pos-1].isspace():
                return

        self.print_command(True)

    def delete(self):
        if self.insert_pos < len(self.line):
            self.line = self.line[:self.insert_pos] + self.line[self.insert_pos+1:]
            self.print_command()

    def delete_until_end(self):
        self.line = self.line[:self.insert_pos]
        self.print_command()

    def delete_word(self):
        found_space = False
        while self.insert_pos < len(self.line) - 1:
            self.line = self.line[:self.insert_pos] + self.line[self.insert_pos+1:]

            if self.line[self.insert_pos].isspace():
                found_space = True
            elif found_space:
                break

        self.print_command()

    def history_back(self):
        if self.history_position > -len(self.lines_history):
            self.history_position -= 1
            self.line = list(self.lines_history[self.history_position])

        self.insert_pos = len(self.line)
        self.print_command()

    def history_forward(self):
        if self.history_position < -1:
            self.history_position += 1
            self.line = list(self.lines_history[self.history_position])

        elif self.history_position == -1:
            # New line
            self.history_position = 0
            self.line = []

        self.insert_pos = len(self.line)
        self.print_command()

    def home(self):
        self.insert_pos = 0
        self.print_command()

    def end(self):
        self.insert_pos = len(self.line)
        self.print_command()

    def cmdloop(self):
        try:
            while True:
                # Set handler for resize terminal events.
                self.pty.set_ssh_channel_size = lambda: self.print_command()

                # Read command
                with raw_mode(self.stdin):
                    result = self.read().strip()

                self.pty.set_ssh_channel_size = None

                # Handle result
                if result:
                    self.lines_history.append(result)
                    self.history_position = 0

                    self.handle([ p for p in result.split(' ') if p ])

        except ExitCLILoop, e:
            print # Print newline
            return e.result

    def exit(self):
        """
        Exit cmd loop.
        """
        raise ExitCLILoop

    def read(self):
        """
        Blocking call which reads in command line input
        Not thread safe
        """
        # Initialize new read
        self.line = []
        self.insert_pos = 0
        self.print_command()

        # Timings
        last_up = time.time()
        last_down = time.time()

        # Interaction loop
        last_char = None
        c = ''
        while True:
            last_char = c

            r, w, e = select([self._extra_stdin, self.stdin], [], [])

            # Receive stream from monitor
            if self._extra_stdin in r:
                self.stdout.write('\x1b[1000D') # Move cursor to the left
                self.stdout.write('\x1b[K') # Erace until the end of line
                self.stdout.write(self._extra_stdin.read(4096))
                self.stdout.write('\r\n')

                # Clear line
                self.print_command()

            if self.stdin in r:
                c = self.stdin.read(1)

                # self.stdout.write(' %i ' % ord(c))
                # self.stdout.flush()
                # continue

                # Contrel-A
                if c == '\x01':
                    self.home()

                # Control-B
                elif c == '\x02':
                    self.cursor_left()

                # Control-C
                elif c == '\x03':
                    self.ctrl_c()

                # Control-D
                elif c == '\x04':
                    self.exit()

                # Contrel-E
                elif c == '\x05':
                    self.end()

                # Control-F
                elif c == '\x06':
                    self.cursor_right()

                # Control-K
                elif c == '\x0b':
                    self.delete_until_end()

                # Control-L
                elif c == '\x0c':
                    self.clear()

                # Control-N
                elif c == '\x0e': # 14
                    self.history_forward()

                # Control-P
                elif c == '\x10': # 16
                    self.history_back()

                # Control-R
                elif c == '\x12': # 18
                    self.stdout.write('\r\nSorry, reverse search is not supported.\r\n')
                    self.print_command()

                # Enter
                elif c in ('\r', '\n'): # Depending on the client \n or \r is sent.
                    # Restore terminal
                    self.stdout.write('\r\n')
                    self.stdout.flush()

                    # Return result
                    return ''.join(self.line)

                # Tab completion
                elif c == '\t':
                    # Double tab press: print all completions and show new prompt.
                    if last_char == '\t':
                        all_completions = self.complete(True)
                        if all_completions:
                            self.print_all_completions(all_completions)
                            self.print_command()

                    else:
                        # Call tab completion
                        append = self.complete()
                        self.line = self.line[:self.insert_pos]

                        for a in append:
                            self.line.append(a)
                            self.insert_pos += 1
                        self.print_command()

                # Backspace
                elif c == '\x7f': # (127) Backspace
                    self.backspace()

                # Escape characters for cursor movement
                elif c == '\x1b': # (27) Escape

                    # When no other characters are followed immediately after the
                    # escape character, we consider it an ESC key press
                    if not select( [self.stdin], [], [], 0)[0]:
                        self.vi_navigation = True
                        c = ''
                    else:
                        c = self.stdin.read(1)

                    if c in ('[', 'O'): # (91, 68)
                        c = self.stdin.read(1)

                        # Cursor to left
                        if c == 'D':
                            self.cursor_left()

                        # Cursor to right
                        elif c == 'C':
                            self.cursor_right()

                        # Cursor up:
                        elif c == 'A':
                            if time.time() - last_up > 0.01:
                                self.history_back()
                            last_up = time.time()

                            # NOTE: When the scrolling events occur too fast,
                            # we'll skip them, because mouse scrolling can generate
                            # multiple up or down events, and we need only
                            # one.

                        # Cursor down:
                        elif c == 'B':
                            if time.time() - last_down > 0.01:
                                self.history_forward()
                            last_down = time.time()

                        # Delete key: esc[3~
                        elif c == '3':
                            c = self.stdin.read(1)

                            if c == '~':
                                self.delete()

                        # xrvt sends esc[7~ for home
                        # some others send esc[1~ (tmux)
                        elif c in ('1', '7'):
                            c = self.stdin.read(1)

                            if c == '~':
                                self.home()

                        # xrvt sends esc[8~ for end
                        # some others send esc[4~ (tmux)
                        elif c in ('4', '8'):
                            c = self.stdin.read(1)

                            if c == '~':
                                self.end()

                        # Home (xterm)
                        if c == 'H':
                            self.home()

                        # End (xterm)
                        elif c == 'F':
                            self.end()

                # Insert character
                else:
                    if self.vi_navigation:
                        if c == 'h': # Move left
                            self.cursor_left()
                        elif c == 'l': # Move right
                            self.cursor_right()
                        elif c == 'I': # Home
                            self.vi_navigation = False
                            self.home()
                        elif c == 'x': # Delete
                            self.delete()
                        elif c == 'A': # Home
                            self.vi_navigation = False
                            self.end()
                        elif c == 'i': # Back to insert mode
                            self.vi_navigation = False
                        elif c == 'a': # Back to insert mode
                            self.vi_navigation = False
                            self.cursor_right()
                        elif c == 'w': # Move word forward
                            self.word_forwards()
                        elif c == 'b': # Move word backwards
                            self.word_backwards()
                        elif c == 'D': # Delete until end
                            self.delete_until_end()
                        elif c == 'd': # Delete
                            c = self.stdin.read(1)
                            if c == 'w': # Delete word
                                self.delete_word()

                    # Only printable characters (space to tilde, or 32..126)
                    elif c >= ' ' and c <= '~':
                        # Note: correct handling of UTF-8 input, can be done
                        # by using the codecs.getreader, but it's complex to
                        # get it working right with the ANSI terminal escape
                        # codes, and buffering, and we don't really need it
                        # anyway.
                        #   # stdin_utf8 = codecs.getreader('utf-8')(sys.stdin)

                        if self.insert_pos < len(self.line):
                            self.line = self.line[:self.insert_pos] + [c] + self.line[self.insert_pos:]
                        else:
                            self.line.append(c)
                        self.insert_pos += 1
                        self.print_command()

                self.stdout.flush()


class HandlerType(object):
    """
    Command line handlers can be given several types.
    This makes it for example possible to the prompt
    another color during execution of a dangerous command.
    """
    color = None

    # A little one character postfix to distinguish between handler types.
    postfix = ''
    postfix_color = None


class NoSubHandler(Exception):
    pass


class Handler(object):
    is_leaf = False
    handler_type = HandlerType()

    def __call__(self):
        raise NotImplementedError

    def complete_subhandlers(self, part):
        """
        Return (name, Handler) subhandler pairs.
        """
        return []

    def get_subhandler(self, name):
        raise NoSubHandler
