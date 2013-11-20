
import StringIO
import os
import paramiko
import threading

from deployer.console import Console
from functools import wraps

from .base import Host, Stat

__all__ = (
    'SSHHost',
)


_ssh_backends = { } # Maps Host class to SSHBackend instances.


class SSHBackend(object):
    """
    Manage Paramiko's SSH connection for a Host.

    When multiple instances of the same SSHHost are created, they will all
    share the same backend (this class). Only one ssh connection per host
    will be created, and shared between all threads.
    """
    def __init__(cls, host_cls):
        pass # Leave __init__ empty, use __new__ for this singleton.

    def __new__(cls, host_cls):
        """
        Create singleton SSHBackend
        """
        if host_cls not in _ssh_backends:
            self = object.__new__(cls, host_cls)

            # Initialize
            self._ssh_cache = None
            self._lock = threading.Lock()

            _ssh_backends[host_cls] = self
        return _ssh_backends[host_cls]

    def __del__(self):
        # Terminate Paramiko's SSH thread
        if self._ssh_cache:
            self._ssh_cache.close()
            self._ssh_cache = None

    def get_ssh(self, host):
        """
        Ssh connection. The actual connection to the host is established
        only after the first call of this function.
        """
        # Lock: be sure not to create this connection from several threads at
        # the same time.
        with self._lock:
            if not (self._ssh_cache and self._ssh_cache._transport and self._ssh_cache._transport.is_active()):
                # Create progress bar.
                progress_bar = self._create_connect_progress_bar(host)

                with progress_bar:
                    h = host

                    # Connect
                    self._ssh_cache = paramiko.SSHClient()

                    if not h.reject_unknown_hosts:
                        self._ssh_cache.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                    try:
                        kw = {}

                        if h.config_filename:
                            try:
                                config_file = file(os.path.expanduser(h.config_filename))
                            except IOError:
                                pass
                            else:
                                ssh_config = paramiko.config.SSHConfig()
                                ssh_config.parse(config_file)
                                host_config = ssh_config.lookup(h.address)

                                # Map ssh_config to paramiko config
                                config_map = {
                                        'identityfile': 'key_filename',
                                        'user': 'username',
                                        'port': 'port',
                                        'connecttimeout': 'timeout',
                                        }
                                for ck, pk in config_map.items():
                                    if ck in host_config:
                                        kw[pk] = host_config[ck]

                        if h.port:
                            kw['port'] = h.port
                        if h.username:
                            kw['username'] = h.username
                        if h.timeout:
                            kw['timeout'] = h.timeout

                        # Paramiko's authentication method can be either a public key, public key file, or password.
                        if h.rsa_key:
                            # RSA key
                            rsa_key_file_obj = StringIO.StringIO(h.rsa_key)
                            kw["pkey"] = paramiko.RSAKey.from_private_key(rsa_key_file_obj, h.rsa_key_password)
                        elif h.key_filename:
                            kw["key_filename"] = h.key_filename
                        elif h.password:
                            kw["password"] = h.password

                        # Connect to the SSH server.
                        # We use a patched connect function instead of the connect of paramiko's library,
                        # In order to add the progress bar.
                        from .paramiko_connect_patch import connect as connect_patch
                        kw['progress_bar_callback'] = progress_bar.set_progress

                        #self._ssh_cache.connect = connect_patch
                        connect_patch(self._ssh_cache, h.address, **kw)

                    except (paramiko.SSHException, Exception) as e:
                        self._ssh_cache = None
                        raise Exception('Could not connect to host %s (%s)\n%s' % (h.slug, h.address, unicode(e)))

            return self._ssh_cache

    def get_sftp(self, host):
        """ Return the paramiko SFTPClient for this connection. """
        transport = self.get_ssh(host).get_transport()
        transport.set_keepalive(host.keepalive_interval)
        sftp = paramiko.SFTPClient.from_transport(transport)

#        # Sometimes, Paramiko his sftp.getcwd() returns an empty path.
#        # Probably, because he doesn't know it yet. By calling chdir('.')
#        # we make sure that we have a path.
#        sftp.chdir('.')

        return sftp

    def _create_connect_progress_bar(self, host):
        from deployer.console import ProgressBarSteps
        console = Console(host.pty)
        return console.progress_bar_with_steps('Connecting to %s %s' % (host.address, host.slug), steps=ProgressBarSteps({
            1: "Resolving DNS",
            2: "Creating socket",
            3: "Creating transport",
            4: "Exchanging keys",
            5: "Authenticating" }))


class SSHStat(Stat):
    """
    Stat info for SSH files.
    """
    def __init__(self, stat_result):
        Stat.__init__(self, stat_result, stat_result.filename)


class SSHHost(Host):
    """
    SSH Host.

    For the authentication, it's required to provide either a ``password``, a
    ``key_filename`` or ``rsa_key``. e.g.

    ::

        class WebServer(SSHHost):
            slug = 'webserver'
            password = '...'
            address = 'example.com'
            username = 'jonathan'

    """
    # Base host configuration
    reject_unknown_hosts = False

    config_filename = '~/.ssh/config'
    """ SSH config file (optional) """

    key_filename = None
    """ RSA key filename (optional) """

    rsa_key = None
    """ RSA key. (optional) """

    rsa_key_password = None
    """ RSA key password. (optional) """

    address = 'example.com'
    """ SSH Address """

    username = ''
    """ SSH Username """

    port = 22
    """ SSH Port """

    timeout = 10
    """ Connection timeout in seconds.  """

    keepalive_interval  = 30
    """ SSH keep alive in seconds  """

    def __init__(self, *a, **kw):
        self._backend = SSHBackend(self.__class__)
        self._cached_start_path = None
        Host.__init__(self, *a, **kw)

    def _get_session(self):
        transport = self._backend.get_ssh(self).get_transport()
        transport.set_keepalive(self.keepalive_interval)
        chan = transport.open_session()
        return chan

    @wraps(Host.get_start_path)
    def get_start_path(self):
        if self._cached_start_path is None:
            sftp = self._backend.get_sftp(self)
            sftp.chdir('.')
            self._cached_start_path = sftp.getcwd()
        return self._cached_start_path

    def expand_path(self, path):
        def expand_tilde(p):
            if p.startswith('~/') or p == '~':
                home = self._backend.get_sftp(self).normalize('.')
                return p.replace('~', home, 1)
            else:
                return p

        # Expand remote path, using the current working directory.
        return os.path.join(expand_tilde(self.getcwd()), expand_tilde(path))

    @wraps(Host.stat)
    def stat(self, remote_path):
        sftp = self._backend.get_sftp(self)
        sftp.chdir(self.getcwd())
        s = sftp.lstat(remote_path)
        return SSHStat(s)

    @wraps(Host.listdir)
    def listdir(self, path='.'):
        sftp = self._backend.get_sftp(self)
        sftp.chdir(self.getcwd())
        return sftp.listdir(path)

    @wraps(Host.listdir_stat)
    def listdir_stat(self, path='.'):
        sftp = self._backend.get_sftp(self)
        sftp.chdir(self.getcwd())
        return [ SSHStat(a) for a in sftp.listdir_attr(path) ]

    def _open(self, remote_path, mode):
        return self._backend.get_sftp(self).open(remote_path, mode)

    def start_interactive_shell(self, command=None, initial_input=None, sandbox=False):
        """
        Start /bin/bash and redirect all SSH I/O from stdin and to stdout.
        """
        # Start a new shell using the same dimentions as the current terminal
        height, width = self.pty.get_size()
        chan = self._backend.get_ssh(self).invoke_shell(term=self.term, height=height, width=width)

        # Keep size of local pty and remote pty in sync
        def set_size():
            height, width = self.pty.get_size()
            chan.resize_pty(width=width, height=height)
        self.pty.set_ssh_channel_size = set_size

        # Start logger
        with self.logger.log_run(self, command=command, shell=True, sandboxing=sandbox) as log_entry:
            # When a command has been passed, use 'exec' to replace the current
            # shell process by this command
            if command:
                chan.send('exec %s\n' % command)

            # PTY receive/send loop
            self._posix_shell(chan, log_entry=log_entry, initial_input=initial_input)

            # Retrieve status code
            status_code = chan.recv_exit_status()
            log_entry.set_status_code(status_code)

            self.pty.set_ssh_channel_size = None

            # Return status code
            return status_code

