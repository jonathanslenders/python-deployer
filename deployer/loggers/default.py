from deployer.exceptions import ExecCommandFailed, QueryException
from deployer.loggers import Logger, RunCallback, FileCallback, ForkCallback, Actions
from deployer.exceptions import ActionException
from pygments import highlight
from pygments.formatters import TerminalFormatter as Formatter
from pygments.lexers import PythonTracebackLexer
import sys
import termcolor


class DefaultLogger(Logger):
    """
    The default logger.
    Does only print nice colored logging information in the stdout.
    """
    def __init__(self, stdout=None, print_group=True):
        self._stdout = stdout
                # TODO: wrap this logger into a proxy object which handles the case that the logger socket is closed.
                #       we have that problem sometimes when we write to a named pipe.
                #       (and the other end terminates `cat logfile`.)
        self._group = []
        self.print_group = print_group

    @property
    def stdout(self):
        if self._stdout:
            return self._stdout
        else:
            # If no stdout was given, take what is currently given in
            # sys.stdout. (may be differrent, every time, depending on the
            # thread in which we are logging.)
            return sys.stdout

    def enter_group(self, func_name, *args, **kwargs):
        name = '%s(%s)' % (func_name,
                ', '.join(map(repr, args) + [ '%s=%s' % (k, repr(v)) for k,v in kwargs.items() ]))
        self._group.append(name)

    def leave_group(self):
        self._group.pop()

    def _print(self, *args):
        for a in args:
            self.stdout.write(a)
        self.stdout.flush()

    def _print_start(self, host, command, use_sudo, sandboxing):
        y = lambda msg: termcolor.colored(msg, 'yellow')
        h = lambda msg: termcolor.colored(msg, 'red', attrs=['bold'])

        group = ' >  '.join([ termcolor.colored(g, 'green') for g in self._group ])
        host_str = host.slug

        if use_sudo:
            command = '(sudo) %s' % command

        if sandboxing:
            command = '(sandbox) %s' % command

        if group and self.print_group:
            self.stdout.write('%s\n' % y(group))

        self.stdout.write('%20s ' % h(host_str))
        self.stdout.write('%s\n' % y(command))
        self.stdout.flush()

    def _print_end(self, success):
        self.stdout.write('\033[10000C\033[10D') # Move 1000 columns forward, 10 columns backwards
        self.stdout.write('\x1b[A') # Move cursor one up
        if success:
            self.stdout.write(termcolor.colored('SUCCESS\n', 'green'))
        else:
            self.stdout.write(termcolor.colored('FAILED\n', 'red', 'on_white'))
        self.stdout.flush()

    def log_fork(self, fork_entry):
        self._print(
                termcolor.colored('Forking ', 'green'),
                termcolor.colored('<%s>' % fork_entry.fork_name, 'yellow'),
                termcolor.colored(' in other terminal...\n', 'green'))

        class callback(ForkCallback):
            def __init__(c):
                # For the fork, create a new logger, starting from
                # the same state.
                c.logger = self._get_fork_class()
                c.logger._group = self._group[:]

            def get_fork_logger(c):
                return c.logger
        return callback()

    def _get_fork_class(self):
        return DefaultLogger()

    def log_run(self, run_entry):
        self._print_start(run_entry.host, run_entry.command, run_entry.use_sudo, run_entry.sandboxing)
        return RunCallback(completed=lambda:
            self._print_end(run_entry.status_code == 0))

    def log_file_opened(self, file_entry):
        self._print_start(file_entry.host, {
            Actions.Open: 'Opening file',
            #Actions.Put: 'Uploading file',
            #Actions.Get: 'Downloading file'
            }[ file_entry.entry_type], file_entry.use_sudo, file_entry.sandboxing)

        if file_entry.entry_type == Actions.Open:
            self.stdout.write('  Mode: %s\n' % file_entry.mode)

        if file_entry.local_path:
            self.stdout.write('  Local path: %s\n' % file_entry.local_path)

        if file_entry.remote_path:
            self.stdout.write('  Remote path: %s\n' % file_entry.remote_path)

        self.stdout.flush()

        return FileCallback(file_closed=lambda:
            self._print_end(file_entry.succeeded))

    def log_exception(self, e):
        print_exception(e, self._stdout)


class IndentedDefaultLogger(DefaultLogger):
    """
    Another logger which prints only to the given stdout,
    It will indent the output according to the node/action hierarchy.
    """
    tree_color = 'red'
    hostname_color = 'yellow'
    command_color = 'green'

    def __init__(self, stdout=None):
        DefaultLogger.__init__(self, stdout=stdout)
        self._indent = 0

    def enter_group(self, func_name, *args, **kwargs):
        self._print(termcolor.colored('%s(%s)\n' % (func_name,
                ', '.join(map(repr, args) + [ '%s=%s' % (k, repr(v)) for k,v in kwargs.items() ])), self.tree_color))
        self._indent += 1

    def leave_group(self):
        self._indent -= 1

    def _print(self, *args):
        o = []

        o.append(termcolor.colored(u'\u2502 ' * self._indent + u'\u251c ', self.tree_color).encode('utf-8'))
        for a in args:
            o.append(a)

        self.stdout.write(''.join(o))
        self.stdout.flush()

    def _print_start(self, host, command, use_sudo, sandboxing):
        # Remove newlines
        command = command.replace('\n', '\\n')[0:100]
        if len(command) > 80:
            command = command[:80] + '...'

        self._print(
                termcolor.colored(host.slug, self.hostname_color, attrs=['bold']).ljust(40),
                ' ',
                termcolor.colored(' (sandbox) ' if sandboxing else '        '),
                termcolor.colored(' (sudo) ' if use_sudo else '        ',  attrs=['bold']),
                termcolor.colored(command, self.command_color, attrs=['bold']))

    def _print_end(self, success):
        o = []
        o.append('\033[10000C\033[10D') # Move 1000 columns forward, 10 columns backwards
        o.append(
                termcolor.colored('SUCCESS', 'green') if success else
                termcolor.colored('FAILED', 'red'))
        o.append('\n')
        self.stdout.write(''.join(o))
        self.stdout.flush()

    def _get_fork_class(self):
        # Return dummy logger instance.
        return Logger()


def print_exception(exception, stdout):
    """
    Print a nice exception, and inner exceptions.
    """
    e = exception

    def print_exec_failed_exception(e):
        print
        print termcolor.colored('FAILED !!', 'red', attrs=['bold'])
        print termcolor.colored('Command:     ', 'yellow'),
        print termcolor.colored(e.command, 'red', attrs=['bold'])
        print termcolor.colored('Host:        ', 'yellow'),
        print termcolor.colored(e.host.slug, 'red', attrs=['bold'])
        print termcolor.colored('Status code: ', 'yellow'),
        print termcolor.colored(str(e.status_code), 'red', attrs=['bold'])
        print

    def print_query_exception(e):
        print
        print termcolor.colored('FAILED TO EXECUTE QUERY', 'red', attrs=['bold'])
        print termcolor.colored('Node:        ', 'yellow'),
        print termcolor.colored(repr(e.node), 'red', attrs=['bold'])
        print termcolor.colored('Attribute:   ', 'yellow'),
        print termcolor.colored(e.attr_name, 'red', attrs=['bold'])
        print termcolor.colored('Query:       ', 'yellow'),
        print termcolor.colored(repr(e.query), 'red', attrs=['bold'])
        print termcolor.colored('Filename:     ', 'yellow'),
        print termcolor.colored(e.query._filename, 'red', attrs=['bold'])
        print termcolor.colored('Line:        ', 'yellow'),
        print termcolor.colored(e.query._line, 'red', attrs=['bold'])
        print

        if e.inner_exception:
            print_exception(e.inner_exception)

    def print_action_exception(e):
        if isinstance(e.inner_exception, (ExecCommandFailed, QueryException)):
            print_exception(e.inner_exception)
        else:
            print '-'*79
            print highlight(e.traceback, PythonTracebackLexer(), Formatter())
            print '-'*79

    def print_other_exception(e):
        print
        print e
        print

    def print_exception(e):
        if isinstance(e, ActionException):
            print_action_exception(e)
        elif isinstance(e, ExecCommandFailed):
            print_exec_failed_exception(e)
        elif isinstance(e, QueryException):
            print_query_exception(e)
        else:
            print_other_exception(e)

    print_exception(e)
