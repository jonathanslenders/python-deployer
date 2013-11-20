import getpass
import os
import pexpect
from functools import wraps

from deployer.console import Console
from deployer.exceptions import ExecCommandFailed

from .base import Host, Stat

__all__ = (
    'LocalHost',
)

class LocalStat(Stat):
    """
    Stat info for local files.
    """
    pass


# Global variable for localhost sudo password cache.
_localhost_password = None
_localhost_start_path = os.getcwd()


class LocalHost(Host):
    """
    ``LocalHost`` can be used instead of :class:`SSHHost` for local execution.
    It uses ``pexpect`` underneat.
    """
    slug = 'localhost'
    address = 'localhost'
    start_path = os.getcwd()

    def run(self, *a, **kw):
        if kw.get('use_sudo', False):
            self._ensure_password_is_known()
        return Host.run(self, *a, **kw)

    def expand_path(self, path):
        return os.path.expanduser(path) # TODO: expansion like with SSHHost!!!!

    def _ensure_password_is_known(self):
        # Make sure that we know the localhost password, before running sudo.
        global _localhost_password
        tries = 0

        while _localhost_password is None:
            _localhost_password = Console(self.pty).input('[sudo] password for %s at %s' %
                        (self.username, self.slug), is_password=True)

            # Check password
            try:
                Host._run_silent_sudo(self, 'ls > /dev/null')
            except ExecCommandFailed:
                print 'Incorrect password'
                self._backend.password = None

                tries += 1
                if tries >= 3:
                    raise Exception('Incorrect password')

    @property
    def password(self):
        return _localhost_password

    @property
    def username(self):
        return getpass.getuser()

    def get_start_path(self):
        return _localhost_start_path

    def get_ip_address(self, interface='eth0'):
        # Just return '127.0.0.1'. Laptops are often only connected
        # on wlan0, and looking for eth0 would return an empty string.
        return '127.0.0.1'

    def _get_session(self): # TODO: choose a better API, then paramiko's.
        """
        Return a channel through which we can execute commands.
        It will reserve a pseudo terminal and attach the process
        during exec_command.
        NOTE: The Channel class is actually just made API-compatible
        with the result of Paramiko's transport.open_session()
        """
        # See:
        # http://mail.python.org/pipermail/baypiggies/2010-October/007027.html
        # http://cr.yp.to/docs/selfpipe.html
        class channel(object):
            def __init__(self):
                self._spawn = None
                self._height, self._width = None, None

                # pexpect.spawn sets by default a winsize of 24x80,
                # we want to get the right size immediately.
                class spawn_override(pexpect.spawn):
                    def setwinsize(s, rows=None, cols=None):
                        # Note: This could throw an obscure "close failed in
                        # file object destructor: IOERROR" if we called this
                        # with None values. (We shouldn't do that, but not sure
                        # why it happens.)
                        w = self._width or cols
                        h = self._height or rows
                        if w and h:
                            pexpect.spawn.setwinsize(s, h, w)
                self.spawn_override = spawn_override

            def get_pty(self, term=None, width=None, height=None):
                self.resize_pty(width=width, height=height)

            def recv(self, count=1024):
                try:
                    return self._spawn.read_nonblocking(count)
                except pexpect.EOF:
                    return ''

            def send(self, data):
                return self._spawn.write(data)

            def fileno(self):
                return self._spawn.child_fd

            def resize_pty(self, width=None, height=None):
                self._width, self._height = width, height

                if self._spawn and self._height and self._width:
                    self._spawn.setwinsize(self._height, self._width)

            def exec_command(self, command):
                self._spawn = self.spawn_override('/bin/bash', ['-c', command])#, cwd='/')

                if self._spawn and self._height and self._width:
                    self._spawn.setwinsize(self._height, self._width)

            def recv_exit_status(self):
                # We need to call close() before retreiving the exitstatus of
                # a pexpect spawn.
                self._spawn.close()
                return self._spawn.exitstatus

            # Just for Paramiko's SSH channel compatibility

            def settimeout(self, *a, **kw):
                pass

            @property
            def status_event(self):
                class event(object):
                    def isSet(self):
                        return False
                return event()

        return channel()

    def _open(self, remote_path, mode):
        # Use the builtin 'open'
        return open(remote_path, mode)

    @wraps(Host.stat)
    def stat(self, path):
        try:
            full_path = os.path.join(self.getcwd(), path)
            filename = os.path.split(full_path)[1]
            return LocalStat(os.stat(full_path), filename)
        except OSError as e:
            # Turn OSError in IOError.
            # Paramiko also throws IOError when doing stat calls on remote files.
            # (OSError is only for local system calls and cannot be generalized.)
            raise IOError(e.message)

    @wraps(Host.listdir)
    def listdir(self, path='.'):
        return os.listdir(os.path.join(* [self.getcwd(), path]))

    @wraps(Host.listdir_stat)
    def listdir_stat(self, path='.'):
        return [ self.stat(f) for f in self.listdir() ]

    def start_interactive_shell(self, command=None, initial_input=None):
        """
        Start an interactive bash shell.
        """
        self.run(command='/bin/bash', initial_input=initial_input)
