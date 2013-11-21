from deployer import std

from termcolor import colored
from datetime import datetime

import random

__doc__ = \
"""
The ``console`` object is an interface for user interaction from within a
``Node``. Among the input methods are choice lists, plain text input and password
input.

It has output methods that take the terminal size into account, like pagination
and multi-column display. It takes care of the pseudo terminal underneat.

Example:

::

    class MyNode(Node):
        def do_something(self):
            if self.console.confirm('Should we really do this?', default=True):
                # Do it...
                pass

.. note:: When the script runs in a shell that was started with the
    ``--non-interactive`` option, the default options will always be chosen
    automatically.

"""


class NoInput(Exception):
    pass


class Console(object):
    """
    Interface for user interaction from within a ``Node``.
    """
    def __init__(self, pty):
        self._pty = pty

    @property
    def is_interactive(self):
        """
        When ``False`` don't ask for input and choose the default options when
        possible.
        """
        return self._pty.interactive

    def input(self, label, is_password=False, answers=None, default=None):
        """
        Ask for plain text input. (Similar to raw_input.)

        :param is_password: Show stars instead of the actual user input.
        :type is_password: bool
        :param answers: A list of the accepted answers or None.
        :param default: Default answer.
        """
        stdin = self._pty.stdin
        stdout = self._pty.stdout

        def print_question():
            answers_str = (' [%s]' % (','.join(answers)) if answers else '')
            default_str = (' (default=%s)' % default if default is not None else '')
            stdout.write(colored('  %s%s%s: ' % (label, answers_str, default_str), 'cyan'))
            stdout.flush()

        def read_answer():
            value = ''
            print_question()

            while True:
                c = stdin.read(1)

                # Enter pressed
                if c in ('\r', '\n') and (value or default):
                    stdout.write('\r\n')
                    break

                # Backspace pressed
                elif c == '\x7f' and value:
                    stdout.write('\b \b')
                    value = value[:-1]

                # Valid character
                elif ord(c) in range(32, 127):
                    stdout.write(colored('*' if is_password else c, attrs=['bold']))
                    value += c

                elif c == '\x03': # Ctrl-C
                    raise NoInput

                stdout.flush()

            # Return result
            if not value and default is not None:
                return default
            else:
                return value

        with std.raw_mode(stdin):
            while True:
                if self._pty.interactive:
                    value = read_answer()
                elif default is not None:
                    print_question()
                    stdout.write('[non interactive] %r\r\n' % default)
                    stdout.flush()
                    value = default
                else:
                    # XXX: Asking for input in non-interactive session
                    value = read_answer()

                # Return if valid anwer
                if not answers or value in answers:
                    return value

                # Otherwise, ask again.
                else:
                    stdout.write('Invalid answer.\r\n')
                    stdout.flush()

    def choice(self, question, options, allow_random=False, default=None):
        """
        :param options: List of (name, value) tuples.
        :type options: list
        :param allow_random: If ``True``, the default option becomes 'choose random'.
        :type allow_random: bool
        """
        if len(options) == 0:
            raise NoInput('No options given.')

        if allow_random and default is not None:
            raise Exception("Please don't provide allow_random and default parameter at the same time.")

        # Order options alphabetically
        options = sorted(options, key=lambda i:i[0])

        # Ask for valid input
        while True:
            self._pty.stdout.write(colored('  %s\n' % question, 'cyan'))

            # Print options
            self.lesspipe(('%10i %s' % (i+1, tuple_[0]) for i, tuple_ in enumerate(options)))

            if allow_random:
                default = 'random'
            elif default is not None:
                try:
                    default = [o[1] for o in options ].index(default) + 1
                except ValueError:
                    raise Exception('The default value does not appear in the options list.')

            result = self.input(question, default=('random' if allow_random else default))

            if allow_random and result == 'random':
                return random.choice(options)[1]
            else:
                try:
                    result = int(result)
                    if 1 <= result <= len(options):
                        return options[result - 1][1]
                except ValueError:
                    pass

                self.warning('Invalid input')

    def confirm(self, question, default=None):
        """
        Print this yes/no question, and return ``True`` when the user answers
        'Yes'.
        """
        answer = 'invalid'

        if default is not None:
            assert isinstance(default, bool)
            default = 'y' if default else 'n'

        while answer not in ('yes', 'no', 'y', 'n'):
            answer = self.input(question + ' [y/n]', default=default)

        return answer in ('yes', 'y')

    #
    # Node selector
    #

    def select_node(self, root_node, prompt='Select a node', filter=None):
        """
        Show autocompletion for node selection.
        """
        from deployer.cli import ExitCLILoop, Handler, HandlerType, CLInterface

        class NodeHandler(Handler):
            def __init__(self, node):
                self.node = node

            @property
            def is_leaf(self):
                return not filter or filter(self.node)

            @property
            def handler_type(self):
                class NodeType(HandlerType):
                    color = self.node.get_group().color
                return NodeType()

            def complete_subhandlers(self, part):
                for name, subnode in self.node.get_subnodes():
                    if name.startswith(part):
                        yield name, NodeHandler(subnode)

            def get_subhandler(self, name):
                if self.node.has_subnode(name):
                    subnode = self.node.get_subnode(name)
                    return NodeHandler(subnode)

            def __call__(self, context):
                raise ExitCLILoop(self.node)

        root_handler = NodeHandler(root_node)

        class Shell(CLInterface):
            @property
            def prompt(self):
                return colored('\n%s > ' % prompt, 'cyan')

            not_found_message = 'Node not found...'
            not_a_leaf_message = 'Not a valid node...'

        node_result = Shell(self._pty, root_handler).cmdloop()

        if not node_result:
            raise NoInput

        return self.select_node_isolation(node_result)

    def select_node_isolation(self, node):
        """
        Ask for a host, from a list of hosts.
        """
        from deployer.inspection import Inspector
        from deployer.node import IsolationIdentifierType

        # List isolations first. (This is a list of index/node tuples.)
        options = [
                (' '.join([ '%s (%s)' % (h.slug, h.address) for h in hosts ]), node) for hosts, node in
                Inspector(node).iter_isolations(identifier_type=IsolationIdentifierType.HOST_TUPLES)
                ]

        if len(options) > 1:
            return self.choice('Choose a host', options, allow_random=True)
        else:
            return options[0][1]

    def lesspipe(self, line_iterator):
        """
        Paginator for output. This will print one page at a time. When the user
        presses a key, the next page is printed. ``Ctrl-c`` or ``q`` will quit
        the paginator.

        :param line_iterator: A generator function that yields lines (without
                              trailing newline)
        """
        stdin = self._pty.stdin
        stdout = self._pty.stdout
        height = self._pty.get_size()[0] - 1

        with std.raw_mode(stdin):
            lines = 0
            for l in line_iterator:
                # Print next line
                stdout.write(l)
                stdout.write('\r\n')
                lines += 1

                # When we are at the bottom of the terminal
                if lines == height:
                    # Wait for the user to press enter.
                    stdout.write(colored('  Press enter to continue...', 'cyan'))
                    stdout.flush()

                    try:
                        c = stdin.read(1)

                        # Control-C or 'q' will quit pager.
                        if c in ('\x03', 'q'):
                            stdout.write('\r\n')
                            stdout.flush()
                            return
                    except IOError:
                        # Interupted system call.
                        pass

                    # Move backwards and erase until the end of the line.
                    stdout.write('\x1b[40D\x1b[K')
                    lines = 0
            stdout.flush()

    def in_columns(self, item_iterator, margin_left=0):
        """
        :param item_iterator: An iterable, which yields either ``basestring``
                              instances, or (colored_item, length) tuples.
        """
        # Helper functions for extracting items from the iterator
        def get_length(item):
            return len(item) if isinstance(item, basestring) else item[1]

        def get_text(item):
            return item if isinstance(item, basestring) else item[0]

        # First, fetch all items
        all_items = list(item_iterator)

        if not all_items:
            return

        # Calculate the longest.
        max_length = max(map(get_length, all_items)) + 1

        # World per line?
        term_width = self._pty.get_size()[1] - margin_left
        words_per_line = max(term_width / max_length, 1)

        # Iterate through items.
        margin = ' ' * margin_left
        line = [ margin ]
        for i, j in enumerate(all_items):
            # Print command and spaces
            line.append(get_text(j))

            # When we reached the max items on this line, yield line.
            if (i+1) % words_per_line == 0:
                yield ''.join(line)
                line = [ margin ]
            else:
                # Pad with whitespace
                line.append(' ' * (max_length - get_length(j)))

        yield ''.join(line)

    def warning(self, text):
        """
        Print a warning.
        """
        stdout = self._pty.stdout
        stdout.write(colored('*** ', 'yellow'))
        stdout.write(colored('WARNING: ' , 'red'))
        stdout.write(colored(text, 'red', attrs=['bold']))
        stdout.write(colored(' ***\n', 'yellow'))
        stdout.flush()

    def progress_bar(self, message, expected=None, clear_on_finish=False):
        """
        Display a progress bar.
        This should be used as a Python context manager.
        Call the next() method to increase the counter.

        ::

            with console.progress_bar('Looking for nodes') as p:
                for i in range(0, 1000):
                    p.next()
                    ...

        :returns: :class:`ProgressBar` instance.
        """
        return ProgressBar(self._pty, message, expected=expected, clear_on_finish=clear_on_finish)

    def progress_bar_with_steps(self, message, steps):
        """
        Display a progress bar with steps.

        ::

            steps = ProgressBarSteps({
                1: "Resolving address",
                2: "Create transport",
                3: "Get remote key",
                4: "Authenticating" })

            with console.progress_bar_with_steps('Connecting to SSH server', steps=steps) as p:
                ...
                p.set_progress(1)
                ...
                p.set_progress(2)
                ...

        :param steps: :class:`ProgressBarSteps` instance.
        """
        return ProgressBar(self._pty, message, steps=steps)


class ProgressBarSteps(object): # TODO: unittest this class.
    def __init__(self, steps):
        # Validate
        for k,v in steps.items():
            assert isinstance(k, int)
            assert isinstance(v, basestring)

        self._steps = steps

    def get_step_description(self, step):
        return self._steps.get(step, '')

    def get_steps_count(self):
        return max(self._steps.keys())


class ProgressBar(object):
    interval = .1 # Refresh interval

    def __init__(self, pty, message, expected=None, steps=None, clear_on_finish=False):
        if expected and steps:
            raise Exception("Don't give expected and steps parameter at the same time.")

        self._pty = pty
        self.message = message
        self.counter = 0
        self.expected = expected
        self.clear_on_finish = clear_on_finish

        self.done = False
        self._last_print = datetime.now()

        # Duration
        self.start_time = datetime.now()
        self.end_time = None

        # In case of steps
        if steps is not None:
            assert isinstance(steps, ProgressBarSteps)
            self.expected = steps.get_steps_count()

        self.steps = steps

    def __enter__(self):
        self._print()
        return self

    def _print(self):
        if self.expected:
            if self.expected > 0:
                perc = '%s%%' % (self.counter * 100 / self.expected)
            else:
                perc = '??'

            counter_str = '%s/%s [%s completed]' % (self.counter, self.expected, perc)
        else:
            counter_str = '%s' % self.counter

        duration = (self.end_time or datetime.now()) - self.start_time
        duration = str(duration).split('.')[0] # Don't show decimals.

        message = colored('%s:' % self.message, 'cyan')
        counter_str = colored(counter_str, 'cyan', attrs=['bold'])
        duration = colored(duration, 'cyan')

        done = colored(' %s ' % (
                '[DONE]' if self.done else
                '[%s]' % self.steps.get_step_description(self.counter) if self.steps
                else ''), 'green')

        self._pty.stdout.write('\x1b[K%s  %s  [%s] %s\r' % (message, counter_str, duration, done))
        # '\x1b[K' clears the line.

    def next(self):
        """
        Increment progress bar counter.
        """
        self.set_progress(self.counter + 1, rewrite=False)

    def set_progress(self, value, rewrite=True):
        """
        Set counter to this value.
        """
        self.counter = value

        # Only print when the last print was .3sec ago
        delta = (datetime.now() - self._last_print).microseconds / 1000 / 1000.

        if rewrite or delta > self.interval:
            self._print()
            self._last_print = datetime.now()

    def __exit__(self, *a):
        self.done = True
        self.end_time = datetime.now()

        if self.clear_on_finish:
            # Clear the line.
            self._pty.stdout.write('\x1b[K')
        else:
            # Redraw and keep progress bar
            self._print()
            self._pty.stdout.write('\n')
