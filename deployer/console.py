from deployer import std
from termcolor import colored

import sys
import random


# =================[ Text based input ]=================

class NoInput(Exception):
    pass


def input(label, is_password=False, answers=None, default=None):
    """
    Input loop. (like raw_input, but nice colored.)
    'answers' can be either None or a list of the accepted answers.
    """
    def print_question():
        answers_str = (' [%s]' % (','.join(answers)) if answers else '')
        default_str = (' (default=%s)' % default if default else '')
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
        if not value and default:
            return default
        else:
            return value

    with std.raw_mode(sys.stdin):
        while True:
            value = read_answer()

            # Return if valid anwer
            if not answers or value in answers:
                return value

            # Otherwise, ask again.
            else:
                sys.stdout.write('Invalid answer.\r\n')
                sys.stdout.flush()


def confirm(question):
    """
    Print this yes/no question, and return True when the user answers 'yes'.
    """
    answer = 'invalid'

    while answer not in ('yes', 'no', 'y', 'n'):
        answer = input(question + ' [y/n]')

    return answer in ('yes', 'y')


def choice(question, options, allow_random=False):
    """
    `options`: (name, value) list
    """
    if len(options) == 0:
        raise NoInput('No options given.')

    while True:
        sys.stdout.write(colored('  %s\n' % question, 'cyan'))

        for i, tuple_ in enumerate(options):
            sys.stdout.write('%10i %s\n' % (i+1, tuple_[0]))

        result = input(question, default=('random' if allow_random else None))

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


def lesspipe(line_iterator, pty):
    """
    Paginator for output.
    """
    height = pty.get_size()[0] - 1

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

def in_columns(item_iterator, pty, margin_left=0):
    """
    `item_iterator' should be an iterable, which yields either
    basestring, or (colored_item, length)
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
    term_width = pty.get_size()[1] - margin_left
    words_per_line = term_width / max_length

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


def warning(text):
    """
    Print a warning.
    """
    sys.stdout.write(colored('*** ', 'yellow'))
    sys.stdout.write(colored('WARNING: ' , 'red'))
    sys.stdout.write(colored(text, 'red', attrs=['bold']))
    sys.stdout.write(colored(' ***\n', 'yellow'))
    sys.stdout.flush()


#
# Service selector
#

def select_service(pty, root_service, prompt='Select service', filter=None):
    """
    Show autocompletion for service selection.
    """
    from deployer.cli import ExitCLILoop, Handler, HandlerType, CLInterface

    class ServiceHandler(Handler):
        def __init__(self, service):
            self.service = service

        @property
        def is_leaf(self):
            return not filter or filter(self.service)

        @property
        def handler_type(self):
            class ServiceType(HandlerType):
                color = self.service.get_group().color
            return ServiceType()

        def complete_subhandlers(self, part):
            for name, subservice in self.service.get_subservices():
                if name.startswith(part):
                    yield name, ServiceHandler(subservice)

        def get_subhandler(self, name):
            if self.service.has_subservice(name):
                subservice = self.service.get_subservice(name)
                return ServiceHandler(subservice)

        def __call__(self, context):
            raise ExitCLILoop(self.service)

    root_handler = ServiceHandler(root_service)

    class Shell(CLInterface):
        @property
        def prompt(self):
            return colored('\n%s > ' % prompt, 'cyan')

        not_found_message = 'Service not found...'
        not_a_leaf_message = 'Not a valid service...'

    service_result = Shell(pty, root_handler).cmdloop()

    if not service_result:
        raise NoInput

    return select_service_isolation(service_result)


def select_service_isolation(service):
    """
    Ask for a host, from a list of hosts.
    """
    if service._is_isolated:
        return service
    else:
        options = [ (i.name, i.service) for i in service.get_isolations() ]
        return choice('Choose a host', options, allow_random=True)
