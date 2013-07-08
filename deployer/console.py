from deployer import std
from termcolor import colored

import sys
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
        return self._pty.interactive

    def input(self, label, is_password=False, answers=None, default=None):
        """
        Ask for plain text input. (Similar to raw_input.)

        :param is_password: Show stars instead of the actual user input.
        :type is_password: bool
        :param answers: A list of the accepted answers or None.
        :param default: Default answer.
        """
        def print_question():
            answers_str = (' [%s]' % (','.join(answers)) if answers else '')
            default_str = (' (default=%s)' % default if default is not None else '')
            sys.stdout.write(colored('  %s%s%s: ' % (label, answers_str, default_str), 'cyan'))
            sys.stdout.flush()

        def read_answer():
            value = ''
            print_question()

            while True:
                c = sys.stdin.read(1)

                # Enter pressed
                if c in ('\r', '\n') and (value or default):
                    sys.stdout.write('\r\n')
                    break

                # Backspace pressed
                elif c == '\x7f' and value:
                    sys.stdout.write('\b \b')
                    value = value[:-1]

                # Valid character
                elif ord(c) in range(32, 127):
                    sys.stdout.write(colored('*' if is_password else c, attrs=['bold']))
                    value += c

                elif c == '\x03': # Ctrl-C
                    raise NoInput

                sys.stdout.flush()

            # Return result
            if not value and default is not None:
                return default
            else:
                return value

        with std.raw_mode(sys.stdin):
            while True:
                if self._pty.interactive:
                    value = read_answer()
                elif default is not None:
                    print_question()
                    sys.stdout.write('[non interactive] %r\r\n' % default)
                    sys.stdout.flush()
                    value = default
                else:
                    # XXX: Asking for input in non-interactive session
                    value = read_answer()

                # Return if valid anwer
                if not answers or value in answers:
                    return value

                # Otherwise, ask again.
                else:
                    sys.stdout.write('Invalid answer.\r\n')
                    sys.stdout.flush()

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
            sys.stdout.write(colored('  %s\n' % question, 'cyan'))

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

                warning('Invalid input')

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

        return select_node_isolation(node_result)

    def select_node_isolation(self, node):
        """
        Ask for a host, from a list of hosts.
        """
        if node._is_isolated:
            return node
        else:
            options = [ (i.name, i.node) for i in node.get_isolations() ]
            return self.choice('Choose a host', options, allow_random=True)

    def lesspipe(self, line_iterator):
        """
        Paginator for output. This will print one page at a time. When the user
        presses a key, the next page is printed. ``Ctrl-c`` or ``q`` will quit
        the paginator.

        :param line_iterator: A generator function that yields lines (without
                              trailing newline)
        """
        height = self._pty.get_size()[0] - 1

        with std.raw_mode(sys.stdin):
            lines = 0
            for l in line_iterator:
                # Print next line
                sys.stdout.write(l)
                sys.stdout.write('\r\n')
                lines += 1

                # When we are at the bottom of the terminal
                if lines == height:
                    # Wait for the user to press enter.
                    sys.stdout.write(colored('  Press enter to continue...', 'cyan'))
                    sys.stdout.flush()

                    try:
                        c = sys.stdin.read(1)

                        # Control-C or 'q' will quit pager.
                        if c in ('\x03', 'q'):
                            sys.stdout.write('\r\n')
                            sys.stdout.flush()
                            return
                    except IOError, e:
                        # Interupted system call.
                        pass

                    # Move backwards and erase until the end of the line.
                    sys.stdout.write('\x1b[40D\x1b[K')
                    lines = 0
            sys.stdout.flush()

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


# =================[ Text based input ]=================



def warning(text):
    """
    Print a warning.
    """
    sys.stdout.write(colored('*** ', 'yellow'))
    sys.stdout.write(colored('WARNING: ' , 'red'))
    sys.stdout.write(colored(text, 'red', attrs=['bold']))
    sys.stdout.write(colored(' ***\n', 'yellow'))
    sys.stdout.flush()


