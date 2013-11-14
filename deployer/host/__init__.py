
import StringIO
import contextlib
import getpass
import logging
import os
import paramiko
import pexpect
import random
import socket
import termcolor
import threading
import time

from deployer.console import Console
from deployer.exceptions import ExecCommandFailed
from deployer.loggers import DummyLoggerInterface
from deployer.pseudo_terminal import DummyPty, select
from deployer.std import raw_mode
from deployer.utils import esc1

from twisted.internet import fdesc
from functools import wraps


__all__ = (
    'Host',
    'SSHHost',
    'LocalHost',
    'HostContext',
)

__doc__ = \
"""
This module contains the immediate wrappers around the remote hosts and their
terminals. It's possible to run commands on a host directly by using these
classes. As an end-user of this library however, you will call the methods of
:class:`SSHHost` and :class:`LocalHost` through
:class:`deployer.host_container.HostsContainer`, the host proxy of a
:class:`deployer.node.Node`.
"""


class HostContext(object):
    """
    A push/pop stack which keeps track of the context on which commands
    at a host are executed.

    (This is mainly used internally by the library.)
    """
        # TODO: Guarantee thread safety!! When doing parallel deployments, and
        #       several threads act on the same host, things will probably go
        #       wrong...
    def __init__(self, start_path=None):
        self._command_prefixes = []
        self._path = []
        self._env = []

        if start_path:
            self._path.append(start_path)

    def __repr__(self):
        return 'HostContext(prefixes=%r, path=%r, env=%r)' % (
                        self._command_prefixes, self._path, self._env)

    def prefix(self, command):
        """
        Prefix all commands with given command plus ``&&``.

        ::

            with host.prefix('workon environment'):
                host.run('./manage.py migrate')
        """
        class Prefix(object):
            def __enter__(context):
                self._command_prefixes.append(command)

            def __exit__(context, *args):
                self._command_prefixes.pop()
        return Prefix()

    def cd(self, path):
        """
        Execute commands in this directory.
        Nesting of cd-statements is allowed.

        ::

            with host.cd('~/directory'):
                host.run('ls')
        """
        class CD(object):
            def __enter__(context):
                self._path.append(path)

            def __exit__(context, *args):
                self._path.pop()
        return CD()

    def _chdir(self, path):
        """ Move to this directory. Not to be used together with the `cd` context manager. """
        # NOTE: This is used by the sftp shell.
        self._path = [ os.path.join(* self._path + [path]) ]

    def env(self, variable, value, escape=True):
        """
        Set this environment variable
        """
        if value is None:
            value = ''

        if escape:
            value = "'%s'" % esc1(value)

        class ENV(object):
            def __enter__(context):
                self._env.append( (variable, value) )

            def __exit__(context, *args):
                self._env.pop()
        return ENV()


class Host(object):
    """
    Definiton of a remote host. An instance will open an SSH connection
    according to the settings defined in the class definition.
    """
    #class __metaclass__(type):
    #    @property
    #    def slug(self):
    #        return self.__name__

    slug = '' # TODO: maybe deprecate 'slug' and use __class__.__name__ instead.
    """
    The slug should be a unique identifier for the host.
    """

    username = ''
    """
    Username for connecting to the Host
    """

    password = '' # For sudo
    """
    Password for connecting to the host.
    """

    # Terminal to report to use for interactive sessions
    term = os.environ.get('TERM', 'xterm') # xterm, vt100, xterm-256color

    # Magic prompt. We expect this string to not appear in the stdout of
    # random programs. This makes it possible to automatically send the
    # correct password when sudo asks us.
    magic_sudo_prompt = termcolor.colored('[:__enter-sudo-password__:]', 'grey') #, attrs=['concealed'])

    def __init__(self):
        self.dummy_logger = DummyLoggerInterface() # XXX: remove self.dummy_logger variable.
        self.host_context = HostContext()

    def get_start_path(self):
        """
        The path in which commands at the server will be executed.
        by default. (if no cd-statements are used.)
        Usually, this is the home directory.
        """
        raise NotImplementedError
#        return self.get_home_directory(self.username)
#        if self.username:
#            return '~%s' % self.username
#        else:
#            return '~'

    def getcwd(self):
        """
        Return current working directory as absolute path.
        """
        path = os.path.normpath(os.path.join(*[ self.get_start_path() ] + self.host_context._path))
        assert path[0] == '/' # Returns absolute directory.
        return path

    def get_home_directory(self, username=None): # TODO: or use getcwd() on the sftp object??
        # TODO: maybe: return self.expand_path('~%s' % username if username else '~')
        if username:
            return self.run(DummyPty(), 'cd /; echo -n ~%s' % username, sandbox=False)
        else:
            return self.run(DummyPty(), 'cd /; echo -n ~', sandbox=False)

    def exists(self, filename, use_sudo=True, **kw):
        """
        Returns ``True`` when a file named ``filename`` exists on this hosts.
        """
        # Note: the **kw is required for passing in a HostContext.
        try:
            self._run_silent("test -f '%s' || test -d '%s'" % (esc1(filename), esc1(filename)),
                        use_sudo=use_sudo, **kw)
            return True
        except ExecCommandFailed:
            return False

    def get_ip_address(self, interface='eth0'):
        """
        Return internal IP address of this interface.
        """
        # We add "cd /", to be sure that at least no error get thrown because
        # we're in a non existing directory right now.

        return self._run_silent(
                """cd /; /sbin/ifconfig "%s" | grep 'inet ad' | """
                """ cut -d: -f2 | awk '{ print $1}' """ % interface).strip()

    def ifconfig(self):
        """
        Return the network information for this host.

        :returns: A :class:`deployer.utils.IfConfig` instance.
        """
        # We add "cd /", to be sure that at least no error get thrown because
        # we're in a non existing directory right now.
        from deployer.utils import parse_ifconfig_output
        return parse_ifconfig_output(self._run_silent('cd /; /sbin/ifconfig'))

    def _wrap_command(self, command, sandbox):
        """
        Prefix command with cd-statements and variable assignments
        """
        result = []

        # Ensure that the start-path exists (only if one was given. Not for the ~)
#        if self.start_path:
#            result.append("(mkdir -p '%s' 2> /dev/null || true) && " %
#                            esc1(self.expand_path(self.start_path)))

        # Prefix with all cd-statements
        cwd = self.getcwd()
        # TODO: We can't have double quotes around paths,
        #       or shell expansion of '*' does not work.
        #       Make this an option for with cd(path):...
        if sandbox:
            # In sandbox mode, it may be possible that this directory
            # is not yet created, only 'cd' to it when the directory
            # really exists.
            result.append('if [ -d %s ]; then cd %s; fi && ' % (cwd,cwd))
        else:
            result.append('cd %s && ' % cwd)

        # Prefix with variable assignments
        for var, value in self.host_context._env:
            #result.append('%s=%s ' % (var, value))
            result.append("export %s=%s && " % (var, value))

            # We use the export-syntax instead of just the key=value prefix
            # for a command. This is necessary, because in the case of pipes,
            # like, e.g.:     " key=value  yes | command "
            # the variable 'key' will not be passed to the second command.
            #
            # Also, note that the value is not escaped, this allow inclusion
            # of other variables.

        # Add the command itself. Put in between braces to make sure that we
        # get the operator priority right. (if the command itself has an ||
        # operator, it won't otherwise work in combination with cd-statements.)
        result.append('(%s)' % command)

        return ''.join(result)

    def run(self, pty, command='echo "no command given"', use_sudo=False, sandbox=False, interactive=True,
                    logger=None, user=None, ignore_exit_status=False, initial_input=None):
        """
        Execute this shell command on the host.

        :param pty: The pseudo terminal wrapper which handles the stdin/stdout.
        :type pty: :class:`deployer.pseudo_terminal.Pty`
        :param command: The shell command.
        :type command: basestring
        :param use_sudo: Run as superuser.
        :type use_sudo: bool
        :param sandbox: Validate syntax instead of really executing. (Wrap the command in ``bash -n``.)
        :type sandbox: bool
        :param interactive: Start an interactive event loop which allows
                            interaction with the remote command. Otherwise, just return the output.
        :type interactive: bool
        :param logger: The logger interface.
        :type logger: LoggerInterface
        :param initial_input: When ``interactive``, send this input first to the host.
        """
        assert isinstance(command, basestring)

        logger = logger or self.dummy_logger

        # Create new channel for this command
        chan = self._get_session()

        # Run in PTY (Sudo usually needs to be run into a pty)
        if interactive:
            height, width = pty.get_size()
            chan.get_pty(term=self.term, width=width, height=height)

            # Keep size of local pty and remote pty in sync
            def set_size():
                height, width = pty.get_size()
                try:
                    chan.resize_pty(width=width, height=height)
                except paramiko.SSHException, e:
                    # Channel closed. Ignore when channel was already closed.
                    pass
            pty.set_ssh_channel_size = set_size
        else:
            pty.set_ssh_channel_size = lambda:None

        command = " && ".join(self.host_context._command_prefixes + [command])

        # Start logger
        with logger.log_run(self, command=command, use_sudo=use_sudo,
                                sandboxing=sandbox, interactive=interactive) as log_entry:
            # Are we sandboxing? Wrap command in "bash -n"
            if sandbox:
                command = "bash -n -c '%s' " % esc1(command)
                command = "%s;echo '%s'" % (command, esc1(command))

            logging.info('Running "%s" on host "%s" sudo=%r, interactive=%r' %
                            (command, self.slug, use_sudo, interactive))

            # Execute
            if use_sudo:
                # We use 'sudo su' instead of 'sudo -u', because shell expension
                # of ~ is threated differently. e.g.
                #
                # 1. This will still show the home directory of the original user
                # sudo -u 'postgres' bash -c ' echo $HOME '
                #
                # 2. This shows the home directory of the user postgres:
                # sudo su postgres -c 'echo $HOME '
                if interactive:
                    wrapped_command = self._wrap_command((
                                "sudo -p '%s' su '%s' -c '%s'" % (esc1(self.magic_sudo_prompt), esc1(user), esc1(command))
                                #"sudo -u '%s' bash -c '%s'" % (user, esc1(command))
                                if user else
                                "sudo -p '%s' bash -c '%s' " % (esc1(self.magic_sudo_prompt), esc1(command))),
                                sandbox
                                )

                    logging.debug('Running wrapped command "%s"' % wrapped_command)
                    chan.exec_command(wrapped_command)

                # Some commands, like certain /etc/init.d scripts cannot be
                # run interactively. They won't work in a ssh pty.
                else:
                    wrapped_command = self._wrap_command((
                        "echo '%s' | sudo -p '(passwd)' -u '%s' -P %s " % (esc1(self.password), esc1(user), command)
                        if user else
                        "echo '%s' | sudo -p '(passwd)' -S %s " % (esc1(self.password), command)),
                        sandbox
                        )

                    logging.debug('Running wrapped command "%s" interactive' % wrapped_command)
                    chan.exec_command(wrapped_command)
            else:
                chan.exec_command(self._wrap_command(command, sandbox))

            if interactive:
                # Pty receive/send loop
                result = self._posix_shell(pty, chan, log_entry=log_entry, initial_input=initial_input)
            else:
                # Read loop.
                result = []
                while True:
                    # Before calling recv, call select to make sure
                    # the channel is ready to be read. (Trick for
                    # getting the SIGCHLD pipe of Localhost to work.)
                    r, w, e = select([chan], [], [])

                    if chan in r:
                        # Blocking call. Returns when data has been received or at
                        # the end of the channel stream.
                        try:
                            data = chan.recv(1024)
                        except IOError:
                            # In case of localhost: application terminated,
                            # caught in SIGCHLD, and closed slave PTY
                            break

                        if data:
                            result += [data]
                        else:
                            break

                result = ''.join(result)
                log_entry.log_io(result)

                #print result # I don't think we need to print the result of non-interactive runs
                              # In any case self._run_silent_sudo should not
                              # print anything.

            # Retrieve status code
            status_code = chan.recv_exit_status()
            log_entry.set_status_code(status_code)

            pty.set_ssh_channel_size = None

            if status_code and not ignore_exit_status:
                raise ExecCommandFailed(command, self, use_sudo=use_sudo, status_code=status_code, result=result)

        # Return result
        if sandbox:
            return '<Not sure in sandbox>'
        else:
            return result

    def _get_session(self):
        raise NotImplementedError

    def _posix_shell(self, pty, chan, raw=True, log_entry=None, initial_input=None):
        """
        Create a loop which redirects sys.stdin/stdout into this channel.
        The loop ends when channel.recv() returns 0.

        Code inspired by the Paramiko interactive demo.
        """
        result = []
        password_sent = False

        # Make stdin non-blocking. (The select call will already
        # block for us, we want sys.stdin.read() to read as many
        # bytes as possible without blocking.)
        fdesc.setNonBlocking(pty.stdin)

        # Set terminal in raw mode
        if raw:
            context = raw_mode(pty.stdin)
        else:
            context = contextlib.nested()

        with context:
            try:
                chan.settimeout(0.0)

                # When initial input has been given, send this first
                if initial_input:
                    time.sleep(0.2) # Wait a very short while for the channel to be initialized, before sending.
                    chan.send(initial_input)

                reading_from_stdin = True

                # Read/write loop
                while True:
                    # Don't wait for any input when an exit status code has been
                    # set already.
                    if chan.status_event.isSet():
                        break;

                    if reading_from_stdin:
                        r, w, e = select([pty.stdin, chan], [], [])
                    else:
                        r, w, e = select([chan], [], [])

                    # Receive stream
                    if chan in r:
                        try:
                            x = chan.recv(1024)

                            # Received length 0 -> end of stream
                            if len(x) == 0:
                                break

                            # Log received characters
                            log_entry.log_io(x)

                            # Write received characters to stdout and flush
                            while True:
                                try:
                                    pty.stdout.write(x)
                                    break
                                except IOError, e:
                                    # Sometimes, when we have a lot of output, we get here:
                                    # IOError: [Errno 11] Resource temporarily unavailable
                                    # Just waiting a little, and retrying seems to work.
                                    # See also: deployer.run.socket_client for a similar issue.
                                    time.sleep(0.2)

                            pty.stdout.flush()

                            # Also remember received output.
                            # We want to return what's written to stdout.
                            result.append(x)

                            # Do we need to send the sudo password? (It's when the
                            # magic prompt has been detected in the stream) Note
                            # that we only monitor the last part of 'result', it's
                            # a bit fuzzy, but works.
                            if not password_sent and self.magic_sudo_prompt in ''.join(result[-32:]):
                                chan.send(self.password)
                                chan.send('\n')
                                password_sent = True
                        except socket.timeout:
                            pass

                    # Send stream (one by one character)
                    if pty.stdin in r:
                        try:
                            x = pty.stdin.read(1024)

                            # We receive \n from stdin, but \r is required to
                            # send. (Until now, the only place where the
                            # difference became clear is in redis-cli, which
                            # only accepts \r as confirmation.)
                            x = x.replace('\n', '\r')
                        except IOError, e:
                            # What to do with IOError exceptions?
                            # (we see what happens in the next select-call.)
                            continue

                        # Received length 0
                        # There's no more at stdin to read.
                        if len(x) == 0:
                            # However, we should go on processing the input
                            # from the remote end, until the process finishes
                            # there (because it was done or processed Ctrl-C or
                            # Ctrl-D/EOF.)
                            #
                            # The end of the input stream happens when we are
                            # using StringIO at the client side, and we're not
                            # attached to a real pseudo terminal. (For
                            # unit-testing, or background commands.)
                            reading_from_stdin = False
                            continue

                        # Write to channel
                        chan.send(x)

                        # Not sure about this. Sometimes, when pasting large data
                        # in the command line, the many concecutive read or write
                        # commands will make Paramiko hang somehow...  (This was
                        # the case, when still using a blocking pty.stdin.read(1)
                        # instead of a non-blocking readmany.
                        time.sleep(0.01)
            finally:
                # Set blocking again
                fdesc.setBlocking(pty.stdin)

            return ''.join(result)

    # =====[ SFTP operations ]====

    def _expand_local_path(self, path):
        # Only tilde expansion
        return os.path.expanduser(path)

    def expand_path(self, path):
        raise NotImplementedError

    def _tempfile(self):
        """ Return temporary filename """
        return self.expand_path('~/deployer-tempfile-%s-%s' % (time.time(), random.randint(0, 1000000)))

    def get_file(self, remote_path, local_path, use_sudo=False, logger=None, sandbox=False):
        """
        Download this remote_file.
        """
        with self.open(remote_path, 'rb', use_sudo=use_sudo, logger=logger, sandbox=sandbox) as f:
            # Expand paths
            local_path = self._expand_local_path(local_path)

            with open(local_path, 'wb') as f2:
                f2.write(f.read()) # TODO: read/write in chunks and print progress bar.

    def put_file(self, local_path, remote_path, use_sudo=False, logger=None, sandbox=False):
        """
        Upload this local_file to the remote location.
        """
        with self.open(remote_path, 'wb', use_sudo=use_sudo, logger=logger, sandbox=sandbox) as f:
            # Expand paths
            local_path = self._expand_local_path(local_path)

            with open(local_path, 'rb') as f2:
                f.write(f2.read())

    def stat(self, remote_path):
        raise NotImplementedError

    def listdir(self, path):
        raise NotImplementedError

    def _open(self, remote_path, mode):
        raise NotImplementedError

    def open(self, remote_path, mode="rb", use_sudo=False, logger=None, sandbox=False):
        """
        Open file handler to remote file. Can be used both as:

        ::

            with host.open('/path/to/somefile', wb') as f:
                f.write('some content')

        or:

        ::

            host.open('/path/to/somefile', wb').write('some content')
        """
        logger = logger or self.dummy_logger

        # Expand path
        remote_path = self.expand_path(remote_path)

        class RemoteFile(object):
            def __init__(rf):
                rf._is_open = False

                # Log entry
                self._log_entry = logger.log_file(self, mode=mode, remote_path=remote_path,
                                                use_sudo=use_sudo, sandboxing=sandbox)
                self._log_entry.__enter__()

                if sandbox:
                    # Use dummy file in sandbox mode.
                    rf._file = open('/dev/null', mode)
                else:
                    if use_sudo:
                        rf._temppath = self._tempfile()

                        if self.exists(remote_path):
                            # Copy existing file to available location
                            self._run_silent_sudo("cp '%s' '%s' " % (esc1(remote_path), esc1(rf._temppath)))
                            self._run_silent_sudo("chown '%s' '%s' " % (esc1(self.username), esc1(rf._temppath)))
                            self._run_silent_sudo("chmod u+r,u+w '%s' " % esc1(rf._temppath))

                        elif mode.startswith('w'):
                            # Create empty tempfile for writing (without sudo,
                            # using current username)
                            self._run_silent("touch '%s' " % esc1(rf._temppath))
                        else:
                            raise IOError('Remote file: "%s" does not exist' % remote_path)

                        # Open stream to this temp file
                        rf._file = self._open(rf._temppath, mode)
                    else:
                        rf._file = self._open(remote_path, mode)

                rf._is_open = True

            def __enter__(rf):
                return rf

            def __exit__(rf, *a, **kw):
                # Close file at the end of the with-statement
                rf.close()

            def __del__(rf):
                # Close file when this instance is gargage collected.
                # (When open(...).write(...) is used.)
                rf.close()

            def read(rf):
                if rf._is_open:
                    return rf._file.read()
                else:
                    raise IOError('Cannot read from closed remote file')

            def readline(rf):
                if rf._is_open:
                    return rf._file.readline()
                else:
                    raise IOError('Cannot read from closed remote file')

            def write(rf, data):
                if rf._is_open:
                    # On some hosts, Paramiko blocks when writing more than
                    # 1180 bytes at once. Not sure about the reason or the
                    # exact limit, but using chunks of 1024 seems to work
                    # well.
                    if len(data) > 1024:
                        rf._file.write(data[:1024])
                        rf.write(data[1024:])
                    else:
                        rf._file.write(data)
                else:
                    raise IOError('Cannot write to closed remote file')

            def close(rf):
                if rf._is_open:
                    try:
                        rf._file.close()

                        if not sandbox:
                            if use_sudo:
                                # Restore permissions (when this file already existed.)
                                if self.exists(remote_path):
                                    self._run_silent_sudo("chown --reference='%s' '%s' " % (esc1(remote_path), esc1(rf._temppath)))
                                    self._run_silent_sudo("chmod --reference='%s' '%s' " % (esc1(remote_path), esc1(rf._temppath)))

                                # Move tempfile back in place
                                self._run_silent_sudo("mv '%s' '%s' " % (esc1(rf._temppath), esc1(remote_path)))

                            # chmod?
                            # TODO
                    except Exception as e:
                        self._log_entry.complete(False)
                        raise e
                    else:
                        self._log_entry.complete(True)

                self._log_entry.__exit__()
                rf._is_open=False

        return RemoteFile()


    # Some simple wrappers for the commands

    def sudo(self, *args, **kwargs):
        """
        Run this command using sudo.
        """
        kwargs['use_sudo'] = True
        return self.run(*args, **kwargs)

    def _run_silent(self, command, **kw):
        pty = DummyPty()
        kw['interactive'] = False
        kw['logger'] = None
        return self.run(pty, command, **kw)

    def _run_silent_sudo(self, command, **kw):
        kw['use_sudo'] = True
        return self._run_silent(command, **kw)


_ssh_backends = { } # Maps Host class to SSHBackend instances.


class SSHBackend(object):
    """
    Manage Paramiko's SSH connection for a Host.

    When multiple instances of the same SSHHost are created, they will all
    share the same backend (this class). Only one ssh connection per host
    will be created, and shared between all threads.
    """
    def __init__(self, host_cls):
        self._ssh_cache = None
        self._lock = threading.Lock()

    def __new__(self, host_cls):
        # Create singleton SSHBackend
        if host_cls not in _ssh_backends:
            _ssh_backends[host_cls] = object.__new__(self, host_cls)
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
                        from .paramiko_connect import connect as connect_patch
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
        from deployer.pseudo_terminal import Pty
        console = Console(Pty())
        return console.progress_bar_with_steps('Connecting to %s %s' % (host.address, host.slug), steps=ProgressBarSteps({
            1: "Resolving DNS",
            2: "Creating socket",
            3: "Creating transport",
            4: "Exchanging keys",
            5: "Authenticating" }))

class Stat(object):
    """ Base `Stat` class """
    @property
    def is_dir(self):
        raise NotImplementedError

    @property
    def is_file(self):
        raise NotImplementedError

    @property
    def st_size(self):
        raise NotImplementedError

    @property
    def st_uid(self):
        raise NotImplementedError

    @property
    def st_gid(self):
        raise NotImplementedError

    @property
    def st_mode(self):
        raise NotImplementedError


class SSHStat(Stat):
    """
    Stat info for SSH files.
    """
    def __init__(self, ssh_stat):
        self._ssh_stat = ssh_stat

    @property
    def is_dir(self):
        from stat import S_ISDIR
        return S_ISDIR(self._ssh_stat.st_mode)

    @property
    def is_file(self):
        from stat import S_ISREG
        return S_ISREG(self._ssh_stat.st_mode)

    @property
    def st_size(self):
        return self._ssh_stat.st_size

    @property
    def st_uid(self):
        return self._ssh_stat.st_uid

    @property
    def st_gid(self):
        return self._ssh_stat.st_gid

    @property
    def st_mode(self):
        return self._ssh_stat.st_mode


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

    def __init__(self):
        self._backend = SSHBackend(self.__class__)
        self._cached_start_path = None
        Host.__init__(self)

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

    def _open(self, remote_path, mode):
        return self._backend.get_sftp(self).open(remote_path, mode)

    def start_interactive_shell(self, pty, command=None, logger=None, initial_input=None, sandbox=False):
        """
        Start /bin/bash and redirect all SSH I/O from stdin and to stdout.
        """
        logger = logger or self.dummy_logger

        # Start a new shell using the same dimentions as the current terminal
        height, width = pty.get_size()
        chan = self._backend.get_ssh(self).invoke_shell(term=self.term, height=height, width=width)

        # Keep size of local pty and remote pty in sync
        def set_size():
            height, width = pty.get_size()
            chan.resize_pty(width=width, height=height)
        pty.set_ssh_channel_size = set_size

        # Start logger
        with logger.log_run(self, command=command, shell=True, sandboxing=sandbox) as log_entry:
            # When a command has been passed, use 'exec' to replace the current
            # shell process by this command
            if command:
                chan.send('exec %s\n' % command)

            # PTY receive/send loop
            self._posix_shell(pty, chan, log_entry=log_entry, initial_input=initial_input)

            # Retrieve status code
            status_code = chan.recv_exit_status()
            log_entry.set_status_code(status_code)

            pty.set_ssh_channel_size = None

            # Return status code
            return status_code


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

    def run(self, pty, *a, **kw):
        if kw.get('use_sudo', False):
            self._ensure_password_is_known(pty)
        return Host.run(self, pty, *a, **kw)

    def expand_path(self, path):
        return os.path.expanduser(path) # TODO: expansion like with SSHHost!!!!

    def _ensure_password_is_known(self, pty):
        # Make sure that we know the localhost password, before running sudo.
        global _localhost_password
        tries = 0

        while _localhost_password is None:
            _localhost_password = Console(pty).input('[sudo] password for %s at %s' %
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
                    def setwinsize(s, *a, **kw):
                        pexpect.spawn.setwinsize(s, self._height, self._width)
                self.spawn_override = spawn_override

            def get_pty(self, term=None, width=None, height=None):
                self.resize_pty(width=width, height=height)

            def recv(self, count=1024):
                try:
                    return self._spawn.read_nonblocking(count)
                except pexpect.EOF, e:
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

    def listdir(self, path='.'):
        return os.listdir(os.path.join(* [self.getcwd(), path]))

    def start_interactive_shell(self, pty, command=None, logger=None, initial_input=None):
        """
        Start an interactive bash shell.
        """
        self.run(pty, command='/bin/bash', logger=logger, initial_input=initial_input)
