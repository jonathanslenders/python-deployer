"""
Start a deployment shell client.
"""

from StringIO import StringIO
from twisted.internet import fdesc

from deployer.utils import esc1
from setproctitle import setproctitle

import array
import errno
import fcntl
import getpass
import glob
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
        self.exit_status = 0

        # Currently running command
        self.update_process_title()

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

    def update_process_title(self):
        """
        Set process name
        """
        setproctitle('deploy connect --socket "%s"' % self.socket_path)

    @property
    def new_window_command(self):
        """
        When a new window is opened, run this command.
        """
        return "python -c 'from deployer.run.socket_client import start; import sys; start(sys.argv[1])' '%s' " % esc1(self.socket_path)

    def _open_new_window(self, focus=False):
        """
        Open another client in a new window.
        """
        try:
            tmux_env = os.environ.get('TMUX', '')
            xterm_env = os.environ.get('XTERM', '')
            display_env = os.environ.get('DISPLAY', '')
            colorterm_env = os.environ.get('COLORTERM', '')

            if tmux_env:
                # Construct tmux split command
                swap = (' && (tmux last-pane || true)' if not focus else '')
                tiled = ' && (tmux select-layout tiled || true)'

                    # We run the new client in the current PATH variable, this
                    # makes sure that if a virtualenv was activated in a tmux
                    # pane, that we use the same virtualenv for this command.
                path_env = os.environ.get('PATH', '')

                subprocess.call(r'TMUX=%s tmux split-window "PATH=\"%s\" %s" %s %s' %
                        (tmux_env, path_env, self.new_window_command, swap, tiled),
                        shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # When in a gnome-terminal:
            elif display_env and colorterm_env == 'gnome-terminal':
                subprocess.call('gnome-terminal -e "%s" &' % self.new_window_command, shell=True)
            # Fallback to xterm
            elif display_env and xterm_env:
                subprocess.call('xterm -e %s &' % self.new_window_command, shell=True)
            else:
                # Failed, print err.
                sys.stdout.write(
                        'ERROR: Doesn\'t know how to open new terminal. '
                        'TMUX and XTERM environment variables are empty.\r\n')
                sys.stdout.flush()

        except Exception as e:
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
                while True:
                    try:
                        sys.stdout.write(data)
                        break
                    except IOError, e:
                        # Sometimes, when we have a lot of output, we get here:
                        # IOError: [Errno 11] Resource temporarily unavailable
                        # Just waiting a little, and retrying seems to work.
                        # See also: deployer.host.__init__ for a similar issue.
                        time.sleep(0.2)

            elif action == 'open-new-window':
                focus = data['focus']
                self._open_new_window(focus)

            elif action == '_info':
                print termcolor.colored(self.socket_path, 'cyan')
                print '     Created:             %s' % data['created']
                print '     Root node name:      %s' % data['root_node_name']
                print '     Root node module:    %s' % data['root_node_module']
                print '     Processes: (%i)' % len(data['processes'])

                for i, process in enumerate(data['processes']):
                    print '     %i' % i
                    print '     - Node name    %s' % process['node_name']
                    print '     - Node module  %s' % process['node_module']
                    print '     - Running      %s' % process['running']

            elif action == 'set-exit-status':
                self.exit_status = data

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

    def run(self, cd_path=None, action_name=None, parameters=None, open_scp_shell=False):
        """
        Run main event loop.
        """
        if action_name and open_scp_shell:
            raise Exception("Don't provide 'action_name' and 'open_scp_shell' at the same time")

        # Set stdin non blocking and raw
        fdesc.setNonBlocking(sys.stdin)
        tcattr = termios.tcgetattr(sys.stdin.fileno())
        tty.setraw(sys.stdin.fileno())

        # Report size
        self._send_size()

        self.socket.sendall(pickle.dumps(('_start-interaction', {
                'cd_path': cd_path,
                'action_name': action_name,
                'parameters': parameters,
                'open_scp_shell': open_scp_shell,
            })))

        self._read_loop()

        # Reset terminal state
        termios.tcsetattr(sys.stdin, termios.TCSAFLUSH, tcattr)

        # Put the cursor again at the left margin.
        sys.stdout.write('\r\n')

        # Set exit status
        sys.exit(self.exit_status)

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
    """
    List all the servers that are running.
    """
    for path in glob.glob('/tmp/deployer.sock.%s.*' % getpass.getuser()):
        try:
            DeploymentClient(path).ask_info()
        except socket.error, e:
            pass


def start(socket_name, cd_path=None, action_name=None, parameters=None, open_scp_shell=False):
    """
    Start a socket client.
    """
    make_stdin_unbuffered()

    DeploymentClient(socket_name).run(cd_path=cd_path,
                    action_name=action_name, parameters=parameters, open_scp_shell=open_scp_shell)
