from twisted.conch import telnet
from twisted.conch.telnet import StatefulTelnetProtocol, TelnetTransport
from twisted.internet import reactor, abstract, fdesc
from twisted.internet.protocol import ServerFactory

from deployer import std
from deployer.cli import HandlerType
from deployer.console import NoInput, input
from deployer.loggers import Actions
from deployer.loggers import LoggerInterface
from deployer.loggers.default import DefaultLogger
from deployer.pty import Pty
from deployer.shell import Shell, ShellHandler, GroupHandler

from operator import attrgetter

import datetime
import os
import random
import select
import signal
import string
import struct
import sys
import threading
from termcolor import colored


__doc__ = """
Web and telnet server for the deployment scripts.
Note that this module is using global variables, it should
never be initialized more than once.
"""

__all__ = ('start',)


# =================[ Global variables ]=================

# Map sessions id to Session instances
active_sessions = { }

# List of global monitors. (This is for real-time monitoring,
# they don't keep any history.)
monitors = []

# Settings
settings = None

# Authentication backend
backend = None


# =================[ Monitoring ]=================

class Monitor(object):
    """
    Base class for logging interfaces.
    """
    def __init__(self):
        pass

    def log_run(self, session, run):
        return lambda:None

    def log_file_opened(self, session, file_entry):
        return lambda:None

    def session_created(self, session):
        pass

    def session_closed(self, session):
        pass


def say(username, content):
    # Also print in every shell
    for session in active_sessions.values():
        shell = session.shell
        if shell:
            shell.write(colored('%s says: ' % username, 'cyan'))
            shell.write(colored(content, 'yellow')) # TODO: remove ANSI vt100 escape characters from content before printing into shell.

    return 'ok'


# =================[ Shell extensions ]=================

class WebHandlerType(HandlerType):
    color = 'cyan'
    postfix = '~'


class ActiveSessionsHandler(ShellHandler):
    """
    List active deployment sessions. (Telnet + HTTP)
    """
    is_leaf = True
    handler_type = WebHandlerType()

    def __call__(self, context):
        print colored('%-35s %-15s %-30s %-12s %s' % ('Session Id', 'Host', 'Start time', 'Username', 'What'), 'cyan')

        for session in list_active_sessions():
            print '%-35s' % session.id,
            print '%-15s' % session.host,
            print '%-30s' % session.start_time,
            print '%-12s' % session.username,
            print '%s' % ((session.shell.currently_running if session.shell else None) or '(Idle)')


class MonitorHandler(ShellHandler):
    """
    Monitor executed commands on other deployment shells.
    """
    is_leaf = True
    handler_type = WebHandlerType()

    def __call__(self, context):
        # Real stdin/out of the current logging session
        stdin = context.cli.stdin
        stdout = context.cli.stdout

        # Use a pseudo terminal to pass the logging IO from other deployment
        # sessions to this one.
        master, slave = os.openpty()
        slave_stdout = os.fdopen(slave, 'w', 0)
        master_stdin = os.fdopen(master, 'r', 0)
        fdesc.setNonBlocking(master_stdin)

        def now():
            return datetime.datetime.now().strftime('%H:%I:%S')

        # Create monitor handler
        class M(Monitor):
            def __init__(self):
                self.line = 0 # Keep line numbers

                slave_stdout.write("Press 'q' or Ctrl-c to exit the monitor\n")
                slave_stdout.write(colored('%-12s' % 'Username', 'cyan'))
                slave_stdout.write(colored('%-9s' % 'Time', 'cyan'))
                slave_stdout.write(colored('%-17s' % 'Host', 'cyan'))
                slave_stdout.write(colored('%s' % 'Command', 'cyan'))
                slave_stdout.write('\n')
                slave_stdout.flush()

            def _print_username(self, username):
                slave_stdout.write(colored('%-12s' % username, 'magenta'))
                slave_stdout.write(colored('%-9s' % now()))

            def _print_user_and_event(self, username, event):
                self._print_username(username)
                slave_stdout.write(' '*17 + event)
                slave_stdout.flush()

            def _print_status(self, line,  succeeded):
                slave_stdout.write('\0337') # ESC 7: Save cursor position
                slave_stdout.write('\033[%iA' % (self.line-line)) # Move cursor up
                slave_stdout.write('\033[1000C') # Move cursor to end of line
                slave_stdout.write('\033[8D') # Move cursor 8 chars back

                if succeeded:
                    slave_stdout.write(colored('succeeded', 'green'))
                else:
                    slave_stdout.write(colored('failed', 'red'))

                slave_stdout.write('\0338') # ESC 8: Restore cursor position

            def log_run(self, session, run):
                if not run.sandboxing:
                    line = self.line

                    self._print_username(session.username)
                    slave_stdout.write(colored('%-17s' % run.host.slug, 'cyan'))
                    slave_stdout.write(colored('%s' % (' (sudo) ' if run.use_sudo else ''), 'red'))
                    slave_stdout.write(colored(run.command, 'green'))

                    slave_stdout.write('\n')
                    slave_stdout.flush()
                    self.line += 1

                    # TODO: I guess these writes should be atomic (group in
                    # one statement), because they can come from different
                    # threads.

                    def callback():
                        # TODO: Make more generic. We don't want to write to
                        # this logger when it has been closed. It may be
                        # possible that the logger has been disconnected and
                        # removed from the globals loggers list, but the
                        # callback still exists.
                        if not slave_stdout.closed:
                            self._print_status(line, run.succeeded)
                    return callback
                else:
                    return lambda:None

            def log_file_opened(self, session, file_entry):
                if not file_entry.sandboxing:
                    line = self.line

                    self._print_username(session.username)
                    slave_stdout.write(colored('%-17s' % file_entry.host.slug, 'cyan'))
                    slave_stdout.write(colored('%s' % (' (sudo) ' if file_entry.use_sudo else ''), 'red'))

                    if file_entry.entry_type == Actions.Get:
                        slave_stdout.write('Downloading: ')
                        slave_stdout.write(colored(file_entry.remote_path, 'green'))

                    elif file_entry.entry_type == Actions.Put:
                        slave_stdout.write('Uploading: ')
                        slave_stdout.write(colored(file_entry.remote_path, 'green'))

                    elif file_entry.entry_type == Actions.Open:
                        slave_stdout.write('Opening file: ')
                        slave_stdout.write(colored(file_entry.remote_path, 'green'))
                        slave_stdout.write(' mode=')
                        slave_stdout.write(colored(file_entry.mode, 'green'))

                    slave_stdout.write('\n')
                    slave_stdout.flush()
                    self.line += 1

                    def callback():
                        if not slave_stdout.closed:
                            self._print_status(line, file_entry.succeeded)
                    return callback
                else:
                    return lambda:None

            def action_started(self, session, action_entry):
                line = self.line
                if action_entry.sandboxing:
                    self._print_user_and_event(session.username, 'Calling action (in sandbox): %s\n' %
                                    colored(action_entry.command, 'green'))
                else:
                    self._print_user_and_event(session.username, 'Calling action: %s\n' %
                                    colored(action_entry.command, 'green'))

                class Callbacks(object):
                    def succeeded(s, result):
                        if not slave_stdout.closed:
                            self._print_status(line, True)

                    def failed(s, exception):
                        if not slave_stdout.closed:
                            self._print_status(line, False)

                self.line += 1
                return Callbacks()

            def session_created(self, session):
                self.line += 1
                self._print_user_and_event(session.username,
                            'Started session host=%s id=%s\n' % (session.host, session.id))

            def session_closed(self, session):
                self.line += 1
                self._print_user_and_event(session.username,
                            'Closed session host=%s id=%s\n' % (session.host, session.id))

        monitor = M()
        monitors.append(monitor)

        with std.raw_mode(stdin):
            while True:
                r, w, e = select.select([master_stdin, stdin], [], [])

                # Receive stream from monitor
                if master_stdin in r:
                    stdout.write(master_stdin.read(4096))

                if stdin in r:
                    char = stdin.read(1)

                    # Leave monitor when 'q' or Ctrl-C has been pressed.
                    if char in ('q', '\x03'):
                        # Cleanup
                        monitors.remove(monitor)
                        slave_stdout.close()
                        master_stdin.close()
                        return



class ListUsers(ShellHandler):
    handler_type = WebHandlerType()
    is_leaf = True

    def __call__(self, context):
        for user in backend.get_users():
            print user


class DeleteUser(ShellHandler):
    handler_type = WebHandlerType()

    def complete_subhandlers(self, part):
        for username in backend.get_users():
            if username.startswith(part):
                yield username, DeleteUser2(self.shell, username)

    def get_subhandler(self, username):
        if username in backend.get_users():
            return DeleteUser2(self.shell, username)


class DeleteUser2(ShellHandler):
    handler_type = WebHandlerType()
    is_leaf = True

    def __init__(self, shell, username):
        ShellHandler.__init__(self, shell)
        self.username = username

    def __call__(self, context):
        print 'Deleting user: %s' % self.username
        backend.delete_user(self.username)


class SetPassword(ShellHandler):
    handler_type = WebHandlerType()

    def complete_subhandlers(self, part):
        for username in backend.get_users():
            if username.startswith(part):
                yield username, SetPassword2(self.shell, username)

    def get_subhandler(self, username):
        if username in backend.get_users():
            return SetPassword2(self.shell, username)


class SetPassword2(ShellHandler):
    handler_type = WebHandlerType()
    is_leaf = True

    def __init__(self, shell, username):
        ShellHandler.__init__(self, shell)
        self.username = username

    def __call__(self, context):
        password = input('New password for %s' % self.username, True)
        if password:
            backend.set_password(self.username, password)
        else:
            print 'Invalid password given'


class CreateUser(ShellHandler):
    handler_type = WebHandlerType()
    is_leaf = True

    def __call__(self, context):
        print 'Create a new user'
        username = input('Username')
        password = input('Password', True)

        if username and password:
            backend.create_user(username, password)
        else:
            print 'Invalid username/password'


class Users(GroupHandler):
    handler_type = WebHandlerType()
    subhandlers = {
        'list': ListUsers,
        'delete': DeleteUser,
        'create': CreateUser,
        'set-password': SetPassword,
    }


class AdminHandler(GroupHandler):
    handler_type = WebHandlerType()
    subhandlers = {
        'active-sessions': ActiveSessionsHandler,
        'monitor': MonitorHandler,
        'users': Users,
    }


class SayHandler(ShellHandler):
    handler_type = WebHandlerType()
    def get_subhandler(self, data):
        return SaySomethingHandler(self.shell, [data])


class SaySomethingHandler(ShellHandler):
    is_leaf = True

    def __init__(self, shell, data):
        ShellHandler.__init__(self, shell)
        self.data = data

    def get_subhandler(self, data):
        return SaySomethingHandler(self.shell, self.data + [data])

    def __call__(self, context):
        say(self.shell.session.username, ' '.join(self.data))


class WebShell(Shell):
    """
    The shell that we provide via telnet/http exposes some additional
    commands for session and user management and logging.
    """
    @property
    def extensions(self):
        return {
                'admin': AdminHandler,
                'say': SayHandler,
                'w': ActiveSessionsHandler, # Similar to the unix 'w' command
                }


# =================[ Text based authentication ]=================

class NotAuthenticated(Exception):
    pass


def pty_based_auth():
    """
    Show a username/password login prompt.
    Return username when authentication succeeded.
    """
    tries = 0
    while True:
        # Password authentication required for this session?
        sys.stdout.write('\033[2J\033[0;0H') # Clear screen
        sys.stdout.write(colored('Please authenticate\r\n\r\n', 'cyan'))

        if tries:
            sys.stdout.write(colored('  Authentication failed, try again\r\n', 'red'))

        try:
            username = input('Username', False)
            password = input('Password', True)
        except NoInput:
            raise NotAuthenticated

        if backend.authenticate(username, password):
            sys.stdout.write(colored(' ' * 40 + 'Authentication successful\r\n\r\n', 'green'))
            return username
        else:
            tries += 1
            if tries == 3:
                raise NotAuthenticated


# =================[ Session handling ]=================

class Session(object):
    """
    Create a pseudo terminal and run a deployment session in it.
    (using a separate thread.)
    """
    def __init__(self, host, username, command=None,
                        writeCallback=None,
                        doneCallback=None,
                        logCallback=None,
                        requires_authentication=False
                        ):
        self.command = command
        self.doneCallback = doneCallback
        self.host = host
        self.logCallback = logCallback
        self.requires_authentication = requires_authentication
        self.start_time = datetime.datetime.now()
        self.username = username
        self.writeCallback = writeCallback

        # Create session ID
        self.id = random_id()

        # Print info
        sys.__stdout__.write('Starting new session, id=%s\n' % self.id)
        sys.__stdout__.flush()

        # Create PTY
        self.master, self.slave = os.openpty()

        # File descriptors for the shell
        self.shell_in = os.fdopen(self.master, 'w', 0)
        self.shell_out = os.fdopen(self.master, 'r', 0)

        # Wrap shell_out into a TeeStd, to allow other processes
        # to listen along.
        self.shell_out = std.TeeStd(self.shell_out)

        # File descriptors for slave pty.
        stdin = os.fdopen(self.slave, 'r', 0)
        stdout = os.fdopen(self.slave, 'w', 0)

        # Create pty object, for passing to deployment enviroment.
        self.pty = Pty(stdin, stdout)

        # Reference to cli object
        self.shell = None

    def __del__(self):
        # TODO: somehow this Session destructor is never called
        #       when a session quits...
        #       Fix memory leak.
        sys.__stdout__.write('Called session destructor\n')
        sys.__stdout__.flush()

    def start(self):
        # Run command in other thread
        class shellThread(threading.Thread):
            """
            Run the shell in another thread
            """
            def run(thr):
                # Set stdin/out pair for this thread.
                sys.stdout.set_handler(self.pty.stdout)
                sys.stdin.set_handler(self.pty.stdin)

                # Authentication
                if self.requires_authentication:
                    try:
                        self.username = pty_based_auth()
                        authenticated = True
                    except NotAuthenticated:
                        authenticated = False
                else:
                    authenticated = True

                if authenticated:
                    # Create loggers
                    logger_interface = LoggerInterface()

                    in_shell_logger = DefaultLogger(self.pty.stdout, print_group=False)

                    # Monitor
                    for m in monitors:
                        m.session_created(self)

                    # Run shell
                    shell = WebShell(settings, self.pty, logger_interface, username=self.username)

                    shell.session = self # Assign session to shell
                    self.shell = shell

                            # in_shell_logger: Displaying of events in the shell itself
                    logger_interface.attach(in_shell_logger)

                    if self.command:
                        shell.handle(self.command)
                    else:
                        shell.cmdloop()

                    logger_interface.detach(in_shell_logger)

                    # Monitor
                    for m in monitors:
                        m.session_closed(self)

                    # Remove references (shell and session had circular reference)
                    self.shell = None
                    shell.session = None

                # Session done
                del active_sessions[self.id]
                sys.__stdout__.write('Ended session, id=%s...\n' % self.id)
                sys.__stdout__.flush()

                # Write last dummy character to trigger the session_closed.
                # (telnet session will otherwise wait for enter keypress.)
                sys.stdout.write(' ')

                # Remove std handlers for this thread.
                sys.stdout.del_handler()
                sys.stdin.del_handler()

                if self.doneCallback:
                    self.doneCallback()

                # Stop IO reader
                self.reader.stopReading()

        self.thread = shellThread()
        self.thread.start()

        # Keep in global dict
        active_sessions[self.id] = self

        # Start IO reader
        self.reader = SelectableFile(self.shell_out, self.writeCallback)
        self.reader.startReading()


class SelectableFile(abstract.FileDescriptor):
    """
    Monitor a file descriptor, and call the callback
    when something is ready to read from this file.
    """
    def __init__(self, fp, callback):
        self.fp = fp
        fdesc.setNonBlocking(fp)
        self.callback = callback
        self.fileno = self.fp.fileno

        abstract.FileDescriptor.__init__(self, reactor)

    def doRead(self):
        buf = self.fp.read(4096)

        if buf:
            self.callback(buf)


# =================[ Utils ]=================

def random_id():
    """
    Utility for generating 'unique' random IDs.
    """
    return ''.join(random.sample(string.ascii_letters, 32))

def list_active_sessions():
    """
    Return active sessions, sorted by start_time.
    """
    return sorted(active_sessions.values(), key=attrgetter('start_time'))


# =================[ Telnet interface ]=================

class TelnetDeployer(StatefulTelnetProtocol):
    """
    Telnet interface
    """
    def connectionMade(self):
        # Start raw (for the line receiver)
        self.setRawMode()

        # Handle window size answers
        self.transport.negotiationMap[telnet.NAWS] = self.telnet_NAWS

        # Use a raw connection for ANSI terminals, more info:
        # http://tools.ietf.org/html/rfc111/6
        # http://s344.codeinspot.com/q/1492309

        # 255, 253, 34,  /* IAC DO LINEMODE */
        self.transport.do(telnet.LINEMODE)

        # 255, 250, 34, 1, 0, 255, 240 /* IAC SB LINEMODE MODE 0 IAC SE */
        self.transport.requestNegotiation(telnet.LINEMODE, '\0')

        # 255, 251, 1    /* IAC WILL ECHO */
        self.transport.will(telnet.ECHO)

        # Negotiate about window size
        self.transport.do(telnet.NAWS)

        # Start session
        self.session = Session(
                    self.transport.transport.client[0],
                    'telnet',
                    writeCallback=lambda data: self.transport.write(data),
                    doneCallback=lambda: self.transport.loseConnection(),
                    requires_authentication=True)
        self.session.start()

    def connectionLost(self, reason):
        # TODO: close connection
        pass

    def enableRemote(self, option):
        #self.transport.write("You tried to enable %r (I rejected it)\r\n" % (option,))
        return True # TODO:only return True for the values that we accept

    def disableRemote(self, option):
        #self.transport.write("You disabled %r\r\n" % (option,))
        pass
        #return True

    def enableLocal(self, option):
        #self.transport.write("You tried to make me enable %r (I rejected it)\r\n" % (option,))
        return True

    def disableLocal(self, option):
        #self.transport.write("You asked me to disable %r\r\n" % (option,))
        pass
        #return True

    def rawDataReceived(self, data):
        self.session.shell_in.write(data)
        self.session.shell_in.flush()

    def telnet_NAWS(self, bytes):
        # When terminal size is received from telnet client,
        # set terminal size on pty object.
        if len(bytes) == 4:
            width, height = struct.unpack('!HH', ''.join(bytes))
            self.session.pty.set_size(height, width)
        else:
            print ("Wrong number of NAWS bytes")


# =================[ Startup]=================

def start(_settings, _backend, telnet_port=8023):
    """
    Start telnet server
    """
    global settings
    global backend
    backend = _backend

    # Settings
    settings = _settings()

    # Thread sensitive interface for stdout/stdin
    std.setup()

    # Telnet
    telnet_factory = ServerFactory()
    telnet_factory.protocol = lambda: TelnetTransport(TelnetDeployer)

    # Handle signals
    def handle_sigint(signal, frame):
        if active_sessions:
            print 'Running, %i active session(s).' % len(active_sessions)
        else:
            print 'No active sessions, exiting'
            reactor.stop()

    signal.signal(signal.SIGINT, handle_sigint)

    # Run the reactor!
    print 'Listening telnet on localhost:%s...' % telnet_port

    reactor.listenTCP(telnet_port, telnet_factory)
    reactor.run()
