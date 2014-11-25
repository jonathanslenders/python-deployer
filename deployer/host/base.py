
import contextlib
import logging
import os
import paramiko
import random
import socket
import termcolor
import time
from stat import S_ISDIR, S_ISREG

from deployer.console import Console
from deployer.exceptions import ExecCommandFailed
from deployer.loggers import DummyLoggerInterface
from deployer.pseudo_terminal import DummyPty, select
from deployer.std import raw_mode
from deployer.utils import esc1

from StringIO import StringIO
from twisted.internet import fdesc

__all__ = (
    'Host',
    'HostContext',
    'Stat',
)

class HostContext(object):
    """
    A push/pop stack which keeps track of the context on which commands
    at a host are executed.

    (This is mainly used internally by the library.)
    """
        # TODO: Guarantee thread safety!! When doing parallel deployments, and
        #       several threads act on the same host, things will probably go
        #       wrong...
    def __init__(self):
        self._command_prefixes = []
        self._path = []
        self._env = []

    def copy(self):
        """ Create a deep copy. """
        c = HostContext()
        c._command_prefixes = list(self._command_prefixes)
        c._path = list(self._path)
        c._env = list(self._env)
        return c

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

    def cd(self, path, expand=False):
        """
        Execute commands in this directory. Nesting of cd-statements is
        allowed.

        ::

            with host.cd('directory'):
                host.run('ls')

        :param expand: Expand tildes.
        :type expand: bool
        """
        class CD(object):
            def __enter__(context):
                self._path.append((path, expand))

            def __exit__(context, *args):
                self._path.pop()
        return CD()

    def _chdir(self, path):
        """ Move to this directory. Not to be used together with the `cd` context manager. """
        # NOTE: This is used by the sftp shell.
        # TODO: check 'expand' flags.
        self._path = [ (os.path.join(* [p[0] for p in self._path] + [path]), False) ]

    def env(self, variable, value, escape=True):
        """
        Set this environment variable

        ::

            with host.cd('VAR', 'my-value'):
                host.run('echo $VAR')
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


class Stat(object):
    """ Base `Stat` class """
    def __init__(self, stat_result, filename):
        self._stat_result = stat_result
        self.filename = filename

    @property
    def st_size(self):
        """ File size in bytes. """
        return self._stat_result.st_size

    @property
    def st_uid(self):
        """ User ID """
        return self._stat_result.st_uid

    @property
    def st_gid(self):
        """ Group ID """
        return self._stat_result.st_gid

    @property
    def st_mode(self):
        return self._stat_result.st_mode

    @property
    def is_dir(self):
        """ True when this is a directory. """
        return S_ISDIR(self.st_mode)

    @property
    def is_file(self):
        """ True when this is a regular file. """
        return S_ISREG(self.st_mode)


class Host(object):
    """
    Abstract base class for SSHHost and LocalHost.

    :param pty: The pseudo terminal wrapper which handles the stdin/stdout.
    :type pty: :class:`deployer.pseudo_terminal.Pty`
    :param logger: The logger interface.
    :type logger: LoggerInterface

    ::

            class MyHost(SSHHost):
                ...
            my_host = MyHost()
            my_host.run('pwd', interactive=False)
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

    password = ''
    """
    Password for connecting to the host. (for sudo)
    """

    # Magic prompt. We expect this string to not appear in the stdout of
    # random programs. This makes it possible to automatically send the
    # correct password when sudo asks us.
    magic_sudo_prompt = termcolor.colored('[:__enter-sudo-password__:]', 'grey') #, attrs=['concealed'])

    def __init__(self, pty=None, logger=None):
        self.host_context = HostContext()
        self.pty = pty or DummyPty()
        self.logger = logger or DummyLoggerInterface()

    def copy(self, pty=None):
        """
        Create a deep copy of this Host class.
        (the pty-parameter allows to bind it to anothor pty)
        """
        h = self.__class__(pty=(pty or self.pty), logger=self.logger)
        h.host_context = self.host_context.copy()
        return h

    def __repr__(self):
        return 'Host(slug=%r, context=%r)' % (self.slug, self.host_context)

    def get_start_path(self):
        """
        The path in which commands at the server will be executed.
        by default. (if no cd-statements are used.)
        Usually, this is the home directory.
        It should always return an absolute path, starting with '/'
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
        # Get path from host context (expand expandable parts)
        host_context_path = [ (self._expand_tilde(path) if expand else path) for path, expand in self.host_context._path ]

        # Join with start path.
        path = os.path.normpath(os.path.join(*[ self.get_start_path() ] + host_context_path))
        assert path[0] == '/' # Returns absolute directory (get_start_path() should be absolute)
        return path

    def get_home_directory(self, username=None): # TODO: or use getcwd() on the sftp object??
        # TODO: maybe: return self.expand_path('~%s' % username if username else '~')
        if username:
            return self._run_silent('cd /; echo -n ~%s' % username, sandbox=False)
        else:
            return self._run_silent('cd /; echo -n ~', sandbox=False)

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

        :returns: An :class:`IfConfig <deployer.utils.network.IfConfig>` instance.
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

        # Set TERM variable.
        result.append("export TERM=%s && " % self.pty.get_term_var())

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

    def run(self, command, use_sudo=False, sandbox=False, interactive=True,
                    user=None, ignore_exit_status=False, initial_input=None, silent=False):
        """
        Execute this shell command on the host.

        :param command: The shell command.
        :type command: basestring
        :param use_sudo: Run as superuser.
        :type use_sudo: bool
        :param sandbox: Validate syntax instead of really executing. (Wrap the command in ``bash -n``.)
        :type sandbox: bool
        :param interactive: Start an interactive event loop which allows
                            interaction with the remote command. Otherwise, just return the output.
        :type interactive: bool
        :param initial_input: When ``interactive``, send this input first to the host.
        """
        assert isinstance(command, basestring)
        assert not initial_input or interactive # initial_input can only in case of interactive.

        logger = DummyLoggerInterface() if silent else self.logger
        pty = DummyPty() if silent else self.pty

        # Create new channel for this command
        chan = self._get_session()

        # Run in PTY (Sudo usually needs to be run into a pty)
        if interactive:
            height, width = pty.get_size()
            chan.get_pty(term=self.pty.get_term_var(), width=width, height=height)

            # Keep size of local pty and remote pty in sync
            def set_size():
                height, width = pty.get_size()
                try:
                    chan.resize_pty(width=width, height=height)
                except paramiko.SSHException as e:
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
                result = self._posix_shell(chan, initial_input=initial_input)
            else:
                # Read loop.
                result = self._read_non_interactive(chan)

                #print result # I don't think we need to print the result of non-interactive runs
                              # In any case self._run_silent_sudo should not print anything.

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

    def _read_non_interactive(self, channel):
        """ Read data from channel and return output. """
        raise NotImplementedError

    def start_interactive_shell(self, command=None, initial_input=None):
        """
        Start an interactive bash shell.
        """
        raise NotImplementedError

    def _posix_shell(self, chan, raw=True, initial_input=None):
        """
        Create a loop which redirects sys.stdin/stdout into this channel.
        The loop ends when channel.recv() returns 0.

        Code inspired by the Paramiko interactive demo.
        """
        result = []
        password_sent = False

        # Set terminal in raw mode
        if raw:
            context = raw_mode(self.pty.stdin)
        else:
            context = contextlib.nested()

        assert self.pty.set_ssh_channel_size
        with context:
            # Make channel non blocking.
            chan.settimeout(0.0)

            # When initial input has been given, send this first
            if initial_input:
                time.sleep(0.2) # Wait a very short while for the channel to be initialized, before sending.
                chan.send(initial_input)

            reading_from_stdin = True

            # Read/write loop
            while True:
                # Don't wait for any input when an exit status code has been
                # set already. (But still wait for the output to finish.)
                if chan.status_event.isSet():
                    reading_from_stdin = False

                    # When the channel is closed, and there's nothing to read
                    # anymore. We can return what we got from Paramiko. (Not
                    # sure why this happens. Most of the time, select() still
                    # returns and chan.recv() returns an empty string, but when
                    # read_ready is False, select() doesn't return anymore.)
                    if chan.closed and not chan.in_buffer.read_ready():
                        break

                channels = [self.pty.stdin, chan] if reading_from_stdin else [chan]
                r, w, e = select(channels, [], [], 1)
                    # Note the select-timeout. That is required in order to
                    # check for the status_event every second.

                # Receive stream
                if chan in r:
                    try:
                        x = chan.recv(1024)

                        # Received length 0 -> end of stream
                        if len(x) == 0:
                            break

                        # Write received characters to stdout and flush
                        while True:
                            try:
                                self.pty.stdout.write(x)
                                break
                            except IOError as e:
                                # Sometimes, when we have a lot of output, we get here:
                                # IOError: [Errno 11] Resource temporarily unavailable
                                # Just waiting a little, and retrying seems to work.
                                # See also: deployer.run.socket_client for a similar issue.
                                time.sleep(0.2)

                        self.pty.stdout.flush()

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
                # (use 'elif', read stdin only when there is no more output to be received.)
                elif self.pty.stdin in r:
                    try:
                        # Make stdin non-blocking. (The select call already
                        # blocked for us, we want sys.stdin.read() to read
                        # as many bytes as possible without blocking.)
                        try:
                            fdesc.setNonBlocking(self.pty.stdin)
                            x = self.pty.stdin.read(1024)
                        finally:
                            # Set stdin blocking again
                            # (Writing works better in blocking mode.
                            # Especially OS X seems to be very sensitive if we
                            # write lange amounts [>1000 bytes] nonblocking to
                            # stdout. That causes a lot of IOErrors.)
                            fdesc.setBlocking(self.pty.stdin)

                        # We receive \n from stdin, but \r is required to
                        # send. (Until now, the only place where the
                        # difference became clear is in redis-cli, which
                        # only accepts \r as confirmation.)
                        x = x.replace('\n', '\r')
                    except IOError as e:
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

            return ''.join(result)

    # =====[ SFTP operations ]====

    def _expand_local_path(self, path):
        # Only tilde expansion
        return os.path.expanduser(path)

    def _expand_tilde(self, relative_path):
        raise NotImplementedError

    def expand_path(self, path):
        raise NotImplementedError

    def _tempfile(self):
        """ Return temporary filename """
        return self.expand_path('~/deployer-tempfile-%s-%s' % (time.time(), random.randint(0, 1000000)))

    def get_file(self, remote_path, local_path, use_sudo=False, sandbox=False):
        """
        Download this remote_file.
        """
        with self.open(remote_path, 'rb', use_sudo=use_sudo, sandbox=sandbox) as f:
            # Expand paths
            local_path = self._expand_local_path(local_path)

            with open(local_path, 'wb') as f2:
                f2.write(f.read()) # TODO: read/write in chunks and print progress bar.

    def put_file(self, local_path, remote_path, use_sudo=False, sandbox=False):
        """
        Upload this local_file to the remote location.
        """
        with self.open(remote_path, 'wb', use_sudo=use_sudo, sandbox=sandbox) as f:
            # Expand paths
            local_path = self._expand_local_path(local_path)

            with open(local_path, 'rb') as f2:
                f.write(f2.read())

    def stat(self, remote_path):
        raise NotImplementedError

    def listdir(self, path='.'):
        raise NotImplementedError

    def listdir_stat(self, path='.'):
        """
        Return a list of :class:`.Stat` instances for each file in this directory.
        """
        raise NotImplementedError

    def _open(self, remote_path, mode):
        raise NotImplementedError

    def open(self, remote_path, mode="rb", use_sudo=False, sandbox=False):
        """
        Open file handler to remote file. Can be used both as:

        ::

            with host.open('/path/to/somefile', 'wb') as f:
                f.write('some content')

        or:

        ::

            host.open('/path/to/somefile', 'wb').write('some content')
        """
        # Expand path
        remote_path = os.path.normpath(os.path.join(self.getcwd(), self.expand_path(remote_path)))

        class RemoteFile(object):
            def __init__(rf):
                rf._is_open = False

                # Log entry
                self._log_entry = self.logger.log_file(self, mode=mode, remote_path=remote_path,
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

            def read(rf, size=-1):
                if rf._is_open:
                    # Always read in chunks of 1024 bytes and show a progress bar.

                    # Create progress bar.
                    p = Console(self.pty).progress_bar('Downloading data',
                            expected=(size if size >= 0 else None))
                    result = StringIO()

                    with p:
                        while True:
                            if size == 0:
                                break
                            elif size < 0:
                                # If we have to read until EOF, keep reaeding
                                # in chunks of 1024
                                chunk = rf._file.read(1024)
                            else:
                                # If we have to read for a certain size, read
                                # until we reached that size.
                                read_size = min(1024, size)
                                chunk = rf._file.read(read_size)
                                size -= len(chunk)

                            if not chunk: break # EOF
                            result.write(chunk)
                            p.set_progress(result.len)

                    return result.getvalue()
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
                    # well. (and that way we can visualise our progress bar.)

                    # Create progress bar.
                    size=len(data)
                    p = Console(self.pty).progress_bar('Uploading data', expected=size)

                    with p:
                        if len(data) > 1024:
                            while data:
                                p.set_progress(size - len(data), rewrite=False) # Auto rewrite
                                rf._file.write(data[:1024])
                                data = data[1024:]
                        else:
                            rf._file.write(data)
                        p.set_progress(size, rewrite=True)
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
        """sudo(command, use_sudo=False, sandbox=False, interactive=True, user=None, ignore_exit_status=False, initial_input=None, silent=False)

        Wrapper around :func:`~deployer.host.base.Host.run` which uses ``sudo``.
        """
        kwargs['use_sudo'] = True
        return self.run(*args, **kwargs)

    def _run_silent(self, command, **kw):
        kw['interactive'] = False
        kw['silent'] = True
        return self.run(command, **kw)

    def _run_silent_sudo(self, command, **kw):
        kw['interactive'] = False
        kw['use_sudo'] = True
        kw['silent'] = True
        return self.run(command, **kw)
