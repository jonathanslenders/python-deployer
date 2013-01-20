#!/usr/bin/env python

from deployer import std
from deployer.cli import HandlerType
from deployer.daemonize import daemonize
from deployer.shell import Shell, ShellHandler, GroupHandler
from deployer.loggers import LoggerInterface
from deployer.loggers.default import DefaultLogger, IndentedDefaultLogger
from deployer.pty import Pty

from twisted.internet import reactor, defer, abstract, fdesc
from twisted.internet import threads
from twisted.internet.protocol import Protocol, Factory
from twisted.internet.error import CannotListenError

import StringIO
import datetime
import getpass
import os
import pickle
import random
import string
import sys

__all__ = ('start',)


"""
IMPORTANT: This file contains a good mix of event driven (Twisted Matrix) and
           threaded, blocking code. Before changing anything in this file,
           please be aware which code runs in the Twisted reactor and which
           code is forked to threads.
"""


# Consts
OPEN_TERMINAL_TIMEOUT = 2

#
# Shell extensions
#


class SocketHandlerType(HandlerType):
    color = 'cyan'
    postfix = '~'


class NewShell(ShellHandler):
    """
    List the HTTP clients.
    """
    is_leaf = True
    handler_type = SocketHandlerType()

    def __call__(self, context):
        print 'Opening new window...'
        self.shell.session.openNewShellFromThread()

class Jobs(ShellHandler):
    is_leaf = True
    handler_type = SocketHandlerType()

    def __call__(self, context):
        print ' TODO: show running jobs...' # TODO

class Monitor(ShellHandler):
    is_leaf = True
    handler_type = SocketHandlerType()

    def __call__(self, context):
        # Open monitor in new pane.
        def monitor(pty):
            logger = IndentedDefaultLogger(pty.stdout)
            self.shell.logger_interface.attach(logger)
            pty.stdout.write('Press to close logging pane...\n')
            pty.stdin.read(1)
            self.shell.logger_interface.detach(logger)

        self.shell.session.connection.runInNewPtys(monitor, focus=False)

#
# Shell instance.
#

class SocketShell(Shell):
    """
    """
    @property
    def extensions(self):
        return {
                'new': NewShell,
                #'jobs': Jobs,
                'open_monitor': Monitor,
                }


class SocketPty(Pty):
    """
    The Pty object that we pass to every shell.
    """
    def __init__(self, stdin, stdout, run_in_new_pty):
        Pty.__init__(self, stdin, stdout)
        self._run_in_new_ptys = run_in_new_pty

    def run_in_auxiliary_ptys(self, callbacks):
        return self._run_in_new_ptys(callbacks)

    @property
    def auxiliary_ptys_are_available(self):
        return True


#
# Connection Utils.
#

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


class Connection(object):
    """
    Unix socket connection.
    Contains a pseudo terminal which can be used
    for either an interactive session, for logging,
    or for a second parallel deployment.
    """
    def __init__(self, settings, transportHandle, doneCallback):
        self.settings = settings
        self.transportHandle = transportHandle
        self.doneCallback = doneCallback
        self.connection_shell = None

        # Create PTY
        master, self.slave = os.openpty()

        # File descriptors for the shell
        self.shell_in = os.fdopen(master, 'w', 0)
        self.shell_out = os.fdopen(master, 'r', 0)

        # File descriptors for slave pty.
        stdin = os.fdopen(self.slave, 'r', 0)
        stdout = os.fdopen(self.slave, 'w', 0)

        # Create pty object, for passing to deployment enviroment.
        self.pty = SocketPty(stdin, stdout, self.runInNewPtys)

        # Start read loop
        self._startReading()

    def _startReading(self):
        """
        Monitor output of the PTY's master, and send it to the client when
        available.
        """
        # Start IO reader
        def writeCallback(data):
            self.transportHandle('_print', data)
        self.reader = SelectableFile(self.shell_out, writeCallback)
        self.reader.startReading()

    def close(self):
        """
        Called when the the process in this connection is finished.
        """
        # Stop IO reader
        self.reader.stopReading()

        # Callback
        self.doneCallback()

    def __del__(self):
        try:
            self.shell_in.close()
            self.shell_out.close()
        except:
            # Catch the following error. No idea how to solve it right now.
            # .. close failed in file object destructor:
            # .. IOError: [Errno 9] Bad file descriptor
            pass

    def startShell(self, clone_shell=None):
        """
        Start an interactive shell in this connection.
        """
        self.connection_shell = ConnectionShell(self, clone_shell=clone_shell)
        self.connection_shell.startThread()

    def openNewConnection(self, focus=False):
        """
        Tell the client that it should open a new window.
        """
        def _open():
            self.transportHandle('open-new-window', { 'focus': focus })
        reactor.callFromThread(_open)

    def runInNewPtys(self, funcs, focus=False):
        """
        Tell the client to open a new window. When the pty has been received,
        call this function into a new thread.

        To be called from this connection's thread.
        """
        # `funcs` can be a list of callables or a single callable.
        if callable(funcs):
            funcs = [funcs]
        else:
            funcs = funcs[:] # Clone, because we pop.

        def getConnection():
            self.openNewConnection(focus=focus)

            # Blocking call to wait for a new connection
            return PtyManager.getNewConnectionFromThread()

        # Be sure to have all the necessairy connections available for every
        # function. If that's not the case, we should keep this thread
        # blocking, and eventually decide to run this function in our own
        # thread if we can't offload it in a fork.
        connections = []
        for f in funcs:
            try:
                connections.append(getConnection())
            except PtyManager.NoPtyConnection, e:
                # getNewConnection can timeout, when opening a new teminal
                # fails. (In that case we should run functions in our own
                # thread.)
                print 'ERROR: Could not open new terminal window...\n'
                break

        # Result
        results = [] # Final result.
        done_d = defer.Deferred() # Fired when all functions are called.

        # Finish execution countdown
        todo = [len(funcs)]
        def countDown():
            todo[0] -= 1
            if todo[0] == 0:
                done_d.callback(results)

        def thread(f, connection):
            """
            In the new spawned thread.
            """
            # Set stdout/in for this thread.
            sys.stdout.set_handler(connection.pty.stdout)
            sys.stdin.set_handler(connection.pty.stdin)

            # Call function
            try:
                result = f(connection.pty)
            except Exception, e:
                # Just print the exception, it's actually the tasks of the
                # runInNewPtys caller to make sure that all the passed
                # functions don't raise errors, or to implement a global
                # try/catch around in each function.
                # We cannot allow exceptions to propagate any more, as it
                # would leave connections open, and break ForkResult.
                print str(e)
                result = ''

            # Remove std handlers for this thread.
            sys.stdout.del_handler()
            sys.stdin.del_handler()

            # Close connection
            reactor.callFromThread(connection.close)
            return result

        def startAllThreads():
            """
            In the Twisted reactor's thread.
            """
            def startThread(f, conn):
                # Add placeholder in results list (ordered output)
                index = len(results)
                results.append(None)

                # Spawn thread
                d = threads.deferToThread(thread, f, conn)

                # Attach thread-done callbacks
                def done(result):
                    # Save result in correct slot.
                    results[index] = result
                    countDown()

                def err(failure):
                    results[index] = str(failure)
                    countDown()

                # Attach callbacks to these threads.
                d.addCallback(done)
                d.addErrback(err)

            while connections:
                conn = connections.pop()
                f = funcs.pop()
                startThread(f, conn)

        # This is blocking, given that `startAllThreads` will be run in the
        # reactor. Not that we wait for all the spawned threads to finish.
        threads.blockingCallFromThread(reactor, startAllThreads)

        # Call remaining functions in current thread/pty. This is the case when
        # opening new terminals failed.
        def handleRemainingInCurrentPty():
            while funcs:
                f = funcs.pop()
                try:
                    result = f(self.pty)
                    results.append(result)
                except Exception, e:
                    results.append(str(e))
                countDown()
        handleRemainingInCurrentPty()

        class ForkResult(object):
            """
            This ForkResult, containing the state of the thread, will be
            returned from the Twisted's reactor thread, to this connection's
            thread.
            Note that this member methods are probably not run from the reactor.
            """
            def join(self):
                """
                Wait for the thread to finish.
                """
                if todo[0] == 0:
                    return results
                else:
                    return threads.blockingCallFromThread(reactor, lambda: done_d)

            @property
            def result(self):
                if todo[0] == 0:
                    return results
                else:
                    raise AttributeError('Result not yet known. Not all threads have been finished.')

        return ForkResult()


class ConnectionShell(object):
    """
    Start an interactive shell for a connection.
    (using a separate thread.)
    """
    def __init__(self, connection, clone_shell=None):
        self.connection = connection

        # Create loggers
        self.logger_interface = LoggerInterface()

        # Run shell
        self.shell = SocketShell(connection.settings, connection.pty,
                                self.logger_interface, clone_shell=clone_shell)

    def openNewShellFromThread(self):
        """
        Open new interactive shell in a new window.
        (Clone location of current shell.)
        """
        # Ask the client to open a new connection
        self.connection.openNewConnection(focus=True)

        try:
            # Blocking call to wait for a new incoming connection
            new_connection = PtyManager.getNewConnectionFromThread()

            # Start a new shell-thread into this connection.
            ConnectionShell(new_connection, clone_shell=self.shell).startThread()
        except PtyManager.NoPtyConnection, e:
            print 'ERROR: could not open new terminal window...'

    def openNewShellFromReactor(self):
        self.connection.openNewConnection(focus=True)
        d = PtyManager.getNewConnection()

        @d.addCallback
        def openShell(new_connection):
            new_connection.startShell(clone_shell=self.shell)

        @d.addErrback
        def failed(failure):
            # Opening a new shell failed.
            pass

    def startThread(self):
        threads.deferToThread(self.thread)

    def thread(self):
        # Set stdin/out pair for this thread.
        sys.stdout.set_handler(self.connection.pty.stdout)
        sys.stdin.set_handler(self.connection.pty.stdin)

        self.shell.session = self # Assign session to shell

        in_shell_logger = DefaultLogger(print_group=False)
        extra_loggers = self.connection.settings.Meta.extra_loggers

                # in_shell_logger: Displaying of events in shell
        self.logger_interface.attach(in_shell_logger)
        for l in extra_loggers:
            self.logger_interface.attach(l)

        self.shell.cmdloop()

        self.logger_interface.detach(in_shell_logger)
        for l in extra_loggers:
            self.logger_interface.detach(l)

        # Remove references (shell and session had circular reference)
        self.shell.session = None
        self.shell = None

        # Remove std handlers for this thread.
        sys.stdout.del_handler()
        sys.stdin.del_handler()

        # Close connection
        reactor.callFromThread(self.connection.close)


class PtyManager(object):
    need_pty_callback = None

    class NoPtyConnection(Exception):
        pass

    @classmethod
    def getNewConnectionFromThread(cls):
        """
        Block the caller's thread, until a new pty has been received.
        It will ask the current shell to open a new terminal,
        and wait for a new socket connection which will initialize
        the new pseudo terminal.
        """
        return threads.blockingCallFromThread(reactor, cls.getNewConnection)

    @classmethod
    def getNewConnection(cls):
        d = defer.Deferred()

        def callback(connection):
            cls.need_pty_callback = None
            timeout.cancel()
            d.callback(connection)

        def timeout():
            cls.need_pty_callback = None
            d.errback(cls.NoPtyConnection())

        timeout = reactor.callLater(OPEN_TERMINAL_TIMEOUT, timeout)

        cls.need_pty_callback = staticmethod(callback)
        return d


class CliClientProtocol(Protocol):
    def __init__(self):
        self._buffer = []
        self.connection = None
        self.created = datetime.datetime.now()

    def dataReceived(self, data):
        try:
            # Try to parse what we have received until now
            io = StringIO.StringIO(''.join(self._buffer + [data]))

            action, data = pickle.load(io)

            # Unmarshalling succeeded, call callback
            if action == '_input':
                self.connection.shell_in.write(data)

            elif action == '_resize':
                self.connection.pty.set_size(*data)

            elif action == '_get_info':
                # Return information to client.
                self._handle('_info', {
                            'created': self.created.isoformat(),
                            # TODO: also return information about running ConnectionShell
                            # objects.
                    })
                self.transport.loseConnection()

            elif action == 'open-new-window':
                print 'opening new window...'
                # When the client wants to open a new shell (Ctrl-N press for
                # instance), check whether we are in an interactive session,
                # and if so, copy this shell.
                if self.connection.connection_shell:
                    self.connection.connection_shell.openNewShellFromReactor()
                else:
                    self._handle('open-new-window', { 'focus': True })

            elif action == '_start-interaction':
                print 'creating session'

                # The defer to thread method, which will be called back
                # immeditiately, can hang if the thread pool has been
                # saturated. Therefor we show this message instead.
                self._handle('_print', 'Waiting for thread to start...\r\n')

                # When a new Pty was needed by an existing shell. (For instance, for
                # a parallel session. Report this connection; otherwise start a new
                # ConnectionShell.
                if PtyManager.need_pty_callback:
                    PtyManager.need_pty_callback(self.connection)
                else:
                    self.connection.startShell()

            # Keep the remainder for the next time.
            remainder = io.read()
            self._buffer = [ remainder ]

            # In case we did receive multiple calls
            # one chunk, immediately parse again.
            if len(remainder):
                self.dataReceived('')
        except (EOFError, ValueError), e:
            # Not enough data, wait for the next part to arrive
            if data:
                self._buffer.append(data)

    def connectionLost(self, reason):
        """
        Disconnected from client.
        """
        print 'Connection lost'

        # Remove current connection from the factory's connection pool.
        self.factory.connectionPool.remove(self.connection)
        self.connection = None

        # When no more connections are left, close the reactor.
        if len(self.factory.connectionPool) == 0 and self.factory.shutdownOnLastDisconnect:
            print 'Stopping server.'
            reactor.stop()

    def _handle(self, action, data):
        self.transport.write(pickle.dumps((action, data)) )

    def connectionMade(self):
        self.connection = Connection(self.factory.settings, self._handle, self.transport.loseConnection)
        self.factory.connectionPool.add(self.connection)


def startSocketServer(settings, shutdownOnLastDisconnect):
    """
    Bind the first available unix socket.
    Return the path.
    """
    # Create protocol factory.
    factory = Factory()
    factory.connectionPool = set() # List of currently, active connections
    factory.protocol = CliClientProtocol
    factory.shutdownOnLastDisconnect = shutdownOnLastDisconnect
    factory.settings = settings

    # Search for a socket to listen on.
    i = 0
    path = None
    while True:
        try:
            path = '/tmp/deployer.sock.%s.%i' % (getpass.getuser(), i)
            reactor.listenUNIX(path, factory)
            print 'Listening on: %s' % path
            break
        except CannotListenError, e:
            i += 1

            # When 100 times failed, cancel server
            if i == 100:
                print '100 times failed to listen on posix socket. Please clean up old sockets.'
                raise

    return path


# =================[ Startup]=================

def start(settings, daemonized=False, shutdown_on_last_disconnect=False, thread_pool_size=50):
    """
    Start web server
    If daemonized, this will start the server in the background,
    and return the socket path.
    """
    # Create settings instance
    settings = settings()

    # Start server
    path = startSocketServer(settings, shutdownOnLastDisconnect=shutdown_on_last_disconnect)

    def run_server():
        # Thread sensitive interface for stdout/stdin
        std.setup()

        # Set thread pool size (max parrallel interactive processes.)
        if thread_pool_size:
            reactor.suggestThreadPoolSize(thread_pool_size)

        # Run Twisted reactor
        reactor.run()

    if daemonized:
        if daemonize():
            # In daemon
            run_server()
            sys.exit()
        else:
            # In parent.
            return path
    else:
        run_server()


if __name__ == '__main__':
    from deployer.contrib.default_config import example_settings
    start(settings=example_settings)
