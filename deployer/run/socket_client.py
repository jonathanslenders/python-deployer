#!/usr/bin/env python

"""
Start a deployment shell client.
"""

from StringIO import StringIO
from twisted.internet import fdesc

import array
import errno
import fcntl
import getopt
import getpass
import glob
import inspect
import os
import pickle
import select
import signal
import socket
import subprocess
import sys
import termcolor
import termios
import time
import tty

__all__ = ('start',)

def get_size():
    # Buffer for the C call
    buf = array.array('h', [0, 0, 0, 0 ])

    # Do TIOCGWINSZ (Get)
    fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, buf, True)

    # Return rows, cols
    return buf[0], buf[1]

def make_stdin_unbuffered():
    # Make stdin/stdout unbufferd
    sys.stdin = os.fdopen(sys.stdin.fileno(), 'r', 0)
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

class DeploymentClient(object):
    def __init__(self, socket_path):
        self.socket_path = socket_path
        self._buffer = []

        # Connect to unix socket
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._connect_socket()

        # Send size to server at startup and when SIGWINCH has been caught.
        def sigwinch_handler(n, frame):
            self._send_size()

        signal.signal(signal.SIGWINCH, sigwinch_handler)

    def _connect_socket(self):
        # Can throw socket.error
        self.socket.connect(self.socket_path)

        # Wait for server to become ready
        time.sleep(0.1)

    def _send_size(self):
        self.socket.sendall(pickle.dumps(('_resize', get_size())))

    @property
    def new_window_command(self):
        """
        When a new window is opened, run this command.
        """
        # Note: we use inspect, instead of __file__, because __file can
        # return pyc files.
        path = inspect.getfile(inspect.currentframe())
        return "python %s -c %s" % (path, self.socket_path)

    def _open_new_window(self, focus=False):
        """
        Open another client in a new window.
        """
        try:
            tmux_env = os.environ.get('TMUX', '')
            xterm_env = os.environ.get('XTERM', '')
            if tmux_env:
                # Construct tmux split command
                swap = (' && (tmux last-pane || true)' if not focus else '')
                tiled = ' && (tmux select-layout tiled || true)'

                    # We run the new client in the current PATH variable, this
                    # makes sure that if a virtualenv was activated in a tmux
                    # pane, that we use the same virtualenv for this command.
                path_env = os.environ.get('PATH', '')

                subprocess.call(r'TMUX=%s tmux split-window "PATH=\"%s\" %s" %s %s' % (tmux_env, path_env, self.new_window_command, swap, tiled),
                        shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            elif xterm_env:
                # When in a gnome-terminal:
                if os.environ.get('COLORTERM', '') == 'gnome-terminal':
                    subprocess.call('gnome-terminal -e "%s" &' % self.new_window_command, shell=True)
                # Fallback to xterm
                else:
                    subprocess.call('xterm -e %s &' % self.new_window_command, shell=True)
            else:
                # Failed, print err.
                sys.stdout.write(
                        'ERROR: Doesn\'t know how to open new terminal. '
                        'TMUX and XTERM environment variables are empty.\r\n')
                sys.stdout.flush()

        except Exception, ex:
            # TODO: Somehow, the subprocess.call raised an IOError Invalid argument,
            # we don't know why, but need to debug when it happens again.
            import pdb; pdb.set_trace()

    def _receive(self, data):
        """
        Process incoming data
        """
        try:
            io = StringIO(''.join(self._buffer + [data]))
            action, data = pickle.load(io)

            # Unmarshalling succeeded, call callback
            if action == '_print':
                sys.stdout.write(data)

            elif action == 'open-new-window':
                focus = data['focus']
                self._open_new_window(focus)

            elif action == '_info':
                print termcolor.colored(self.socket_path, 'cyan')
                print '     created: %s' % data['created']
                #print '|%s|' % data # TODO: print more nicely formatted.

            # Keep the remainder for the next time
            remainder = io.read()
            self._buffer = [ remainder ]

            if len(remainder):
                self._receive('')
        except (EOFError, ValueError), e:
            # Not enough data, wait for the next part to arrive
            if data:
                self._buffer.append(data)

    def ask_info(self):
        self.socket.sendall(pickle.dumps(('_get_info', '')))
        self._read_loop()

    def run(self, command=None):
        """
        Run main event loop.
        """
        # Set stdin non blocking and raw
        fdesc.setNonBlocking(sys.stdin)
        tcattr = termios.tcgetattr(sys.stdin.fileno())
        tty.setraw(sys.stdin.fileno())

        # Report size
        self._send_size()

        self.socket.sendall(pickle.dumps(('_start-interaction', '')))

        # Send command to server if one was given.
        if command:
            self.socket.sendall(pickle.dumps(('_input', '%s\n' % command)))

        self._read_loop()
        sys.stdout.write('\n')

        # Reset terminal state
        termios.tcsetattr(sys.stdin, termios.TCSAFLUSH, tcattr)

    def _read_loop(self):
        while True:
            try:
                # I/O routing
                r, w, e = select.select([ self.socket, sys.stdin ], [], [])

                if self.socket in r:
                    data = self.socket.recv(1024)
                    if data:
                        self._receive(data)
                    else:
                        # Nothing received? End of stream.
                        break

                if sys.stdin in r:
                    data = sys.stdin.read(1)
                    if ord(data) == 14: # Ctrl-N
                        # Tell the server to open a new window.
                        self.socket.sendall(pickle.dumps(('open-new-window', '')))
                    else:
                        self.socket.sendall(pickle.dumps(('_input', data)))

            except socket.error:
                print '\nConnection closed...'
                break
            except Exception as e:
                # SIGWINCH will abort select() call. Just ignore this error
                if e.args and e.args[0] == errno.EINTR:
                    continue
                else:
                    raise


def list_sessions():
    for path in glob.glob('/tmp/deployer.sock.%s.*' % getpass.getuser()):
        try:
            DeploymentClient(path).ask_info()
        except socket.error, e:
            pass


def start(settings_module):
    """
    Client startup point.
    """
    make_stdin_unbuffered()

    run_command = None
    socket_name = ''

    def print_usage():
        print 'Usage:'
        print '    ./client.py [-h|--help] [ -c|--connect "socket number" ] [ -r|--run "command" ] [ -l | --list-sessions ]'

    # Parse command line arguments.
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hr:c:l', ['help', 'run=', 'connect=', 'list-sessions'])
    except getopt.GetoptError, err:
        print str(err)
        print_usage()
        sys.exit(2)

    for o, a in opts:
        if o in ('-h', '--help'):
            print_usage()
            sys.exit()

        elif o in ('-r', '--run'):
            run_command = a

        elif o in ('-l', '--list-sessions',):
            list_sessions()
            sys.exit()

        elif o in ('-c', '--connect'):
            socket_name = a

    # If no socket has been given. Start a daemonized server in the
    # background, and use that socket instead.
    if not socket_name:
        from deployer.run.socket_server import start
        socket_name = start(settings_module, daemonized=True, shutdown_on_last_disconnect=True)

    # The socket path can be an absolute path, or an integer.
    if not socket_name.startswith('/'):
        socket_name = '/tmp/deployer.sock.%s.%s' % (getpass.getuser(), socket_name)

    DeploymentClient(socket_name).run(command=run_command)


if __name__ == '__main__':
    from deployer.contrib.default_config import example_settings
    start(settings_module=example_settings)
