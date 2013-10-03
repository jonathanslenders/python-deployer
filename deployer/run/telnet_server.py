from twisted.conch import telnet
from twisted.conch.telnet import StatefulTelnetProtocol, TelnetTransport
from twisted.internet import reactor, abstract, fdesc
from twisted.internet.protocol import ServerFactory
from twisted.internet.threads import deferToThread

from deployer import std
from deployer.cli import HandlerType
from deployer.console import NoInput, Console
from deployer.loggers import LoggerInterface
from deployer.loggers.default import DefaultLogger
from deployer.pseudo_terminal import Pty
from deployer.shell import Shell, ShellHandler

from contextlib import nested
from termcolor import colored
from setproctitle import setproctitle

import logging
import os
import signal
import struct
import sys


__doc__ = """
Web and telnet server for the deployment scripts.
Note that this module is using global variables, it should
never be initialized more than once.
"""

__all__ = ('start',)


# =================[ Authentication backend ]=================

class Backend(object):
    def authenticate(self, username, password):
        # Return True when this username/password combination is correct.
        raise NotImplementedError

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

    def __call__(self):
        print colored('%-12s %s' % ('Username', 'What'), 'cyan')

        for session in self.shell.session.protocol.factory.connectionPool:
            print '%-12s' % (session.username or 'somebody'),
            print '%s' % ((session.shell.currently_running if session.shell else None) or '(Idle)')


class WebShell(Shell):
    """
    The shell that we provide via telnet/http exposes some additional
    commands for session and user management and logging.
    """
    @property
    def extensions(self):
        return { 'w': ActiveSessionsHandler, }

    def __init__(self, *a, **kw):
        username = kw.pop('username')
        Shell.__init__(self, *a, **kw)
        self.username = username

    @property
    def prompt(self):
        """
        Return a list of [ (text, color) ] tuples representing the prompt.
        """
        if self.username:
            return [ (self.username, 'cyan'), ('@', None) ] + super(WebShell, self).prompt
        else:
            return super(WebShell, self).prompt

# =================[ Text based authentication ]=================

class NotAuthenticated(Exception):
    pass


def pty_based_auth(auth_backend, pty):
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
            console = Console(pty)
            username = console.input('Username', False)
            password = console.input('Password', True)
        except NoInput:
            raise NotAuthenticated

        if auth_backend.authenticate(username, password):
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
    def __init__(self, protocol, writeCallback=None, doneCallback=None):
        self.protocol = protocol
        self.root_node = protocol.transport.factory.root_node
        self.auth_backend = protocol.transport.factory.auth_backend
        self.extra_loggers = protocol.transport.factory.extra_loggers

        self.doneCallback = doneCallback
        self.writeCallback = writeCallback
        self.username = None

        # Create PTY
        self.master, self.slave = os.openpty()

        # File descriptors for the shell
        self.shell_in = self.shell_out = os.fdopen(self.master, 'r+w', 0)

        # File descriptors for slave pty.
        stdin = stdout = os.fdopen(self.slave, 'r+w', 0)

        # Create pty object, for passing to deployment enviroment.
        self.pty = Pty(stdin, stdout)

    def start(self):
        def thread():
            """
            Run the shell in a normal synchronous thread.
            """
            # Set stdin/out pair for this thread.
            sys.stdout.set_handler(self.pty.stdout)
            sys.stdin.set_handler(self.pty.stdin)

            # Authentication
            try:
                self.username = pty_based_auth(self.auth_backend, self.pty) if self.auth_backend else ''
                authenticated = True
            except NotAuthenticated:
                authenticated = False

            if authenticated:
                # Create loggers
                logger_interface = LoggerInterface()
                in_shell_logger = DefaultLogger(self.pty.stdout, print_group=False)

                # Run shell
                shell = WebShell(self.root_node, self.pty, logger_interface, username=self.username)

                shell.session = self # Assign session to shell
                self.shell = shell

                with logger_interface.attach_in_block(in_shell_logger):
                    with nested(* [logger_interface.attach_in_block(l) for l in self.extra_loggers]):
                        shell.cmdloop()

                # Remove references (shell and session had circular reference)
                self.shell = None
                shell.session = None

            # Write last dummy character to trigger the session_closed.
            # (telnet session will otherwise wait for enter keypress.)
            sys.stdout.write(' ')

            # Remove std handlers for this thread.
            sys.stdout.del_handler()
            sys.stdin.del_handler()

            if self.doneCallback:
                self.doneCallback()

            # Stop IO reader
            reactor.callFromThread(self.reader.stopReading)

        deferToThread(thread)

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

# =================[ Telnet interface ]=================

class TelnetDeployer(StatefulTelnetProtocol):
    """
    Telnet interface
    """
    def connectionMade(self):
        logging.info('Connection made, starting new session')

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
        self.session = Session(self,
                    writeCallback=lambda data: self.transport.write(data),
                    doneCallback=lambda: self.transport.loseConnection())
        self.factory.connectionPool.add(self.session)
        self.session.start()

    def connectionLost(self, reason):
        self.factory.connectionPool.remove(self.session)
        logging.info('Connection lost. Session ended')

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
            print "Wrong number of NAWS bytes"


# =================[ Startup]=================

def start(root_node, auth_backend=None, port=8023, logfile=None, extra_loggers=None):
    """
    Start telnet server
    """
    # Set logging
    if logfile:
        logging.basicConfig(filename=logfile, level=logging.DEBUG)
    else:
        logging.basicConfig(filename='/dev/stdout', level=logging.DEBUG)

    # Thread sensitive interface for stdout/stdin
    std.setup()

    # Telnet
    factory = ServerFactory()
    factory.connectionPool = set() # List of currently, active connections
    factory.protocol = lambda: TelnetTransport(TelnetDeployer)
    factory.root_node = root_node()
    factory.auth_backend = auth_backend
    factory.extra_loggers = extra_loggers or []

    # Handle signals
    def handle_sigint(signal, frame):
        if factory.connectionPool:
            logging.info('Running, %i active session(s).' % len(factory.connectionPool))
        else:
            logging.info('No active sessions, exiting')
            reactor.stop()

    signal.signal(signal.SIGINT, handle_sigint)

    # Run the reactor!
    logging.info('Listening for incoming telnet connections on localhost:%s...' % port)

    # Set process name
    suffix = (' --log "%s"' % logfile if logfile else '')
    setproctitle('deploy:%s telnet-server --port %i%s' %
            (root_node.__class__.__name__, port, suffix))

    # Run server
    reactor.listenTCP(port, factory)
    reactor.run()
