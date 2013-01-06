#!/usr/bin/env python

__doc__ = """
Pure Python alternative to readline and cmm.Cmd.

Author: Jonathan Slenders
"""


import codecs
import os
import sys
import termcolor
import termios
import tty
import time

from twisted.internet import fdesc
from deployer.pty import select
from deployer.std import raw_mode
from deployer.console import in_columns, lesspipe


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


class CallContext(object):
    def __init__(self, parts, cli):
        self.command = ' '.join(parts)
        self.cli = cli


class CLInterface(object):
    """
    A pure-python implementation of a command line completion interface.
    It does not rely on readline or raw_input, which don't offer
    autocompletion in Python 2.6/2.7 when different ptys are used in different
    threads.
    """
    prompt = '>'
    not_found_message = 'Command not found...'
    not_a_leaf_message = 'Incomplete command...'

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
        self.terminal_pos = 0
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
                h(CallContext(parts=original_parts, cli=self))
                self.currently_running = None
            else:
                print self.not_a_leaf_message
        else:
            print self.not_found_message

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

        lesspipe(in_columns(column_items(), self.pty), self.pty)

    def ctrl_c(self):
        # Initialize new read
        self.line = []
        self.insert_pos = 0
        self.terminal_pos = 0
        self.history_position = 0
        self.vi_navigation = False

        # Print promt again
        self.stdout.write('\r\n')
        self.print_prompt()

    def print_prompt(self):
        # Print prompt
        self.stdout.write(self.prompt)
        self.terminal_pos = 0

        # Reprint current string
        self.print_command()

    def print_command(self):
        """
        Reprint command (what's after the prompt), using syntax highlighting.
        """
        # We have an unbufferred stdout, so it's faster to write only once.
        out = []

        # Move cursor position to the left.
        if self.terminal_pos:
            out.append('\x1b[%iD' % self.terminal_pos) # Move 'pos' positions backwards

        out.append('\x1b[K') # Erace until the end of line

        # Print complete command line
        line = ''.join(self.line)
        h = self.root
        while line:
            if line[0].isspace():
                out.append(line[0])
                line = line[1:]
            else:
                # First following part
                p = line.split()[0]
                line = line[len(p):]

                if h:
                    try:
                        h = h.get_subhandler(p)

                        if h:
                            out.append(termcolor.colored(p, h.handler_type.color))
                        else:
                            out.append(p)
                    except (NotImplementedError, NoSubHandler):
                        h = None
                        out.append(p)
                else:
                    out.append(p)

        # Move cursor to correct position
        pos = len(self.line)
        if pos > self.insert_pos + 1:
            out.append('\x1b[%iD' % (pos - self.insert_pos)) # Move positions backwards
        self.terminal_pos = self.insert_pos

        # Flush buffer
        self.stdout.write(''.join(out))
        self.stdout.flush()

    def clear(self):
        # Erase screen and move cursor to 0,0
        self.stdout.write('\033[2J\033[0;0H')
        self.print_prompt()

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
            self.terminal_pos -= 1
            self.stdout.write('\x1b[D') # Move to left

    def cursor_right(self):
        if self.insert_pos < len(self.line):
            self.insert_pos += 1
            self.terminal_pos += 1
            self.stdout.write('\x1b[C') # Move to right

    def word_forwards(self):
        found_space = False
        while self.insert_pos < len(self.line) - 1:
            self.insert_pos += 1
            self.terminal_pos += 1
            self.stdout.write('\x1b[C') # Move to right

            if self.line[self.insert_pos].isspace():
                found_space = True
            elif found_space:
                return

    def word_backwards(self):
        found_non_space = False
        while self.insert_pos > 0:
            self.insert_pos -= 1
            self.terminal_pos -= 1
            self.stdout.write('\x1b[D') # Move to left

            if not self.line[self.insert_pos].isspace():
                found_non_space = True
            if found_non_space and self.insert_pos > 0 and self.line[self.insert_pos-1].isspace():
                return

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
                with raw_mode(self.stdin):
                    result = self.read().strip()

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
        self.terminal_pos = 0
        self.print_prompt()

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
                self.print_prompt()

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
                    self.print_prompt()

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
                            self.print_prompt()

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

                    if c == '[': # (91)
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

                    elif c == 'O':
                        c = self.stdin.read(1)

                        # Home
                        if c == 'H':
                            self.home()

                        # End
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

    def __call__(self, context):
        raise NotImplementedError

    def complete_subhandlers(self, part):
        """
        Return (name, Handler) subhandler pairs.
        """
        return []

    def get_subhandler(self, name):
        raise NoSubHandler
