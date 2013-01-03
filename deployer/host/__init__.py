

# Features:
#   - logging of all manual activity of all hosts on one central server.
#   - easy configuration
#   - allowing setup of multi-server deployments
#   - should be extensible with a web interface.


import copy
import getpass
import os
import paramiko
import pexpect
import random
import socket
import sys
import termcolor
import termios
import threading
import time
import tty

from deployer.console import input as read_input
from deployer.exceptions import ExecCommandFailed
from deployer.loggers import DummyLoggerInterface, Actions
from deployer.pty import DummyPty, select
from deployer.utils import esc1

from twisted.internet import fdesc

# ================ Hosts =====================================


# Remember instances for the Host classes. Keep them in this global
# dictionary. (Another way would be to save the instance in a mangled name in
# the class itself, but we had some trouble going that way, something with
# inheritance.)
_host_instances = { }


class Host(object):
    """
    Definiton of a remote host. An instance will open an SSH connection
    according to the settings defined in the class definition.
    """
    #class __metaclass__(type):
    #    @property
    #    def slug(self):
    #        return self.__name__

    slug = ''
    username = ''
    password = '' # For sudo

    # Terminal to report to use for interactive sessions
    term = 'xterm' # xterm, vt100, xterm-256color

    # Magic prompt. We expect this string to not appear in the stdout of
    # random programs. This makes it possible to automatically send the
    # correct password when sudo asks us.
    magic_sudo_prompt = termcolor.colored('[:__enter-sudo-password__:]', 'grey') #, attrs=['concealed'])

    def __init__(self):
        """
        Create an instance of this Host class. This will initiate an SSH
        connection.
        """
        # Context
        self._command_prefixes = []
        self._path = [] # cd to this path for every command
        self._env = [] # Environment variables

        # No sandbox
        self._sandboxing = False

        # Dummy logger
        self.dummy_logger = DummyLoggerInterface()

    @classmethod
    def get_instance(cls):
        """
        Return an instance of this host.
        """
        # Singleton class.
        try:
            return _host_instances[cls]
        except KeyError:
            _host_instances[cls] = cls()
            return _host_instances[cls]

    def clone(self):
        """
        Return a new Host() instance, as a copy of this state.
        (Every thread should its own state of every host.)
        """
        new_host = self.__class__()
        self._copy_state_to(new_host)
        return new_host

    def _copy_state_to(self, other_host):
        """
        Copy state from this host to other host.
        """
        for var in ('_command_prefixes', '_path', '_env', '_sandboxing'):
            setattr(other_host, var, copy.copy(getattr(self, var)))

    @property
    def cwd(self):
        """
        Current working directory.
        """
        if self._path:
            return os.path.join(*self._path)
        else:
            return self.get_home_directory()

    def _wrap_command(self, command):
        """
        Prefix command with cd-statements and variable assignments
        """
        result = []

        # Prefix with all cd-statements
        for p in self._path:
            # TODO: We can't have double quotes around paths,
            #       or shell expansion of '*' does not work.
            #       Make this an option for with cd(path):...
            if self._sandboxing:
                # In sandbox mode, it may be possible that this directory
                # is not yet created, only 'cd' to it when the directory
                # really exists.
                result.append('if [ -d %s ]; then cd %s; fi && ' % (p,p))
            else:
                result.append('cd %s && ' % p)

        # Prefix with variable assignments
        for var, value in self._env:
            #result.append('%s=%s ' % (var, value))
            result.append("export %s=%s && " % (var, value))

            # We use the export-syntax instead of just the key=value prefix
            # for a command. This is necessary, because in the case of pipes,
            # like, e.g.:     " key=value  yes | command "
            # the variable 'key' will not be passed to the second command.
            #
            # Also, note that the value is not escaped, this allow inclusion
            # of other variables.

        result.append(command)
        return ''.join(result)

    def _run_silent_sudo(self, command):
        pty = DummyPty()
        return self._run(pty, command, use_sudo=True, interactive=False, logger=None)

    def _run_silent(self, command):
        pty = DummyPty()
        return self._run(pty, command, interactive=False, logger=None)

    def _run(self, pty, command='echo "no command given"', use_sudo=False, interactive=True,
                        logger=None, user=None, ignore_exit_status=False, initial_input=None):
        """
        Execute this command.
        When `interactive`, it will use stdin/stdout and use an interactive loop, otherwise, it will
        return the output.
        When the command fails and ignore_exit_status is false, it will raise ExecCommandFailed
        """
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

        command = " && ".join(self._command_prefixes + [command])

        # Start logger
        with logger.log_run(self, command=command, use_sudo=use_sudo,
                                sandboxing=self._sandboxing, interactive=interactive) as log_entry:
            # Are we sandboxing? Wrap command in "bash -n"
            if self._sandboxing:
                command = "bash -n -c '%s' " % esc1(command)
                command = "%s;echo '%s'" % (command, esc1(command))

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
                    chan.exec_command(self._wrap_command(
                                "sudo -p '%s' su '%s' -c '%s'" % (esc1(self.magic_sudo_prompt), esc1(user), esc1(command))
                                #"sudo -u '%s' bash -c '%s'" % (user, esc1(command))
                                if user else
                                "sudo -p '%s' bash -c '%s' " % (esc1(self.magic_sudo_prompt), esc1(command))
                                ))

                # Some commands, like certain /etc/init.d scripts cannot be
                # run interactively. They won't work in a ssh pty.
                else:
                    chan.exec_command(self._wrap_command(
                        "echo '%s' | sudo -p '(passwd)' -u '%s' -P %s " % (esc1(self.password), esc1(user), command)
                        if user else
                        "echo '%s' | sudo -p '(passwd)' -S %s " % (esc1(self.password), command)
                        ))
            else:
                chan.exec_command(self._wrap_command(command))

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
        if self._sandboxing:
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

        # Save terminal attributes
        oldtty = termios.tcgetattr(pty.stdin)

        # Make stdin non-blocking. (The select call will already
        # block for us, we want sys.stdin.read() to read as many
        # bytes as possible without blocking.)
        fdesc.setNonBlocking(pty.stdin)

        try:
            # Set terminal raw
            if raw:
                tty.setraw(pty.stdin.fileno())
                tty.setcbreak(pty.stdin.fileno())
            chan.settimeout(0.0)

            # When initial input has been given, send this first
            if initial_input:
                time.sleep(0.2) # Wait a very short while for the channel to be initialized, before sending.
                chan.send(initial_input)

            # Read/write loop
            while True:
                # Don't wait for any input when an exit status code has been
                # set already.
                if chan.status_event.isSet():
                    break;

                r, w, e = select([pty.stdin, chan], [], [])

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
                        pty.stdout.write(x)
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
                    except IOError, e:
                        # What to do with IOError exceptions?
                        # (we see what happens in the next select-call.)
                        continue

                    # Received length 0 -> end of stream
                    if len(x) == 0:
                        break

                    # Write to channel
                    chan.send(x)

                    # Not sure about this. Sometimes, when pasting large data
                    # in the command line, the many concecutive read or write
                    # commands will make Paramiko hang somehow...  (This was
                    # the case, when still using a blocking pty.stdin.read(1)
                    # instead of a non-blocking readmany.
                    time.sleep(0.01)
        finally:
            # Restore terminal
            termios.tcsetattr(pty.stdin, termios.TCSADRAIN, oldtty)

        # Set blocking again
        fdesc.setBlocking(pty.stdin)

        return ''.join(result)


    # =====[ Actions which are also available in non-sandbox mode ]====

    def get_ip_address(self, interface='eth0'):
        """
        Return internal IP address of this interface.
        """
        # Add "cd /", to be sure that at least no error get thrown because
        # we're in a non existing directory right now.
        with self.cd('/'):
            with self.sandbox(False):
                # Some hosts give 'inet addr:', other 'enet adr:' back.
                #
                # TODO: probably use the 'ip address show dev eth0' instead.
                return self._run_silent("""/sbin/ifconfig "%s" | grep 'inet ad' | """
                        """ cut -d: -f2 | awk '{ print $1}' """ % interface).strip()

    def get_home_directory(self, username=None):
        with self.cd('/'):
            with self.sandbox(False):
                if username:
                    return self._run_silent('echo -n ~%s' % username)
                else:
                    return self._run_silent('echo -n ~')

    @property
    def hostname(self):
        with self.cd('/'):
            with self.sandbox(False):
                return self._run_silent('hostname').strip()

    @property
    def is_64_bit(self):
        with self.sandbox(False):
            return 'x86_64' in self._run_silent('uname -m')

    # =====[ SFTP operations ]====

    def _expand_local_path(self, path):
        # Only tilde expansion
        return os.path.expanduser(path)

    def expand_path(self, path):
        raise NotImplementedError

    def _tempfile(self):
        """
        Return temporary filename
        """
        return self.expand_path('~/deployer-tempfile-%s-%s' % (time.time(), random.randint(0, 1000000)))

    @property
    def sftp(self):
        raise NotImplementedError

    def get(self, remote_path, local_path, use_sudo=False, logger=None):
        """
        Download this remote_file.
        """
        logger = logger or self.dummy_logger

        # Expand paths
        local_path = self._expand_local_path(local_path)
        remote_path = self.expand_path(remote_path)

        # Log entries
        with logger.log_file(self, Actions.Get, mode='rb', remote_path=remote_path,
                            local_path=local_path, use_sudo=use_sudo, sandboxing=self._sandboxing) as log_entry:
            try:
                if use_sudo:
                    if not self._sandboxing:
                        # Copy file to available location
                        temppath = self._tempfile()
                        self._run_silent_sudo("mv '%s' '%s'" % (esc1(remote_path), esc1(temppath)))
                        self._run_silent_sudo("chown '%s' '%s'" % (esc1(self.username), esc1(temppath)))
                        self._run_silent_sudo("chmod u+r '%s'" % esc1(temppath))

                        # Download file
                        self.get(temppath, local_path)

                        # Remove temp file
                        self._run_silent_sudo('rm "%s"' % temppath)
                else:
                    open(local_path, 'wb').write(self.sftp.open(remote_path, 'rb').read())
            except Exception as e:
                log_entry.complete(False)
                raise e
            else:
                log_entry.complete(True)

    def put(self, local_path, remote_path, use_sudo=False, logger=None):
        """
        Upload this local_file to the remote location.
        """
        logger = logger or self.dummy_logger

        # Expand paths
        local_path = self._expand_local_path(local_path)
        remote_path = self.expand_path(remote_path)

        # Log entry
        with logger.log_file(self, Actions.Put, mode='wb', remote_path=remote_path,
                            local_path=local_path, use_sudo=use_sudo, sandboxing=self._sandboxing) as log_entry:
            try:
                if not self._sandboxing:
                    if use_sudo:
                        # Upload in tempfile
                        temppath = self._tempfile()
                        self.put(local_path, temppath)

                        # Move tempfile to real destination
                        self._run_silent_sudo("mv '%s' '%s'" % (esc1(temppath), esc1(remote_path)))

                        # chmod?
                        # TODO
                    else:
                        self.sftp.open(remote_path, 'wb').write(open(local_path, 'rb').read())
            except Exception as e:
                log_entry.complete(False)
                raise e
            else:
                log_entry.complete(True)

    def open(self, remote_path, mode="rb", use_sudo=False, logger=None):
        """
        Open file handler to remote file. Can be used both as:

        1)

        >> with host.open('/path/to/somefile', wb') as f:
        >>     f.write('some content')

        2)

        >> host.open('/path/to/somefile', wb').write('some content')
        """
        logger = logger or self.dummy_logger

        # Expand path
        remote_path = self.expand_path(remote_path)

        class RemoteFile(object):
            def __init__(rf):
                rf._is_open = False

                # Remember sandboxing state in here. (To make sure it's still
                # the same on __exit__)
                rf._sandboxing = self._sandboxing

                # Log entry
                self._log_entry = logger.log_file(self, Actions.Open, mode=mode, remote_path=remote_path,
                                                use_sudo=use_sudo, sandboxing=rf._sandboxing)
                self._log_entry.__enter__()

                if rf._sandboxing:
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
                            raise Exception('Remote file: "%s" does not exist' % remote_path)

                        # Open stream to this temp file
                        rf._file = self.sftp.open(rf._temppath, mode)
                    else:
                        rf._file = self.sftp.open(remote_path, mode)

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
                    raise Exception('Cannot read from closed remote file')

            def readline(rf):
                if rf._is_open:
                    return rf._file.readline()
                else:
                    raise Exception('Cannot read from closed remote file')

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
                    raise Exception('Cannot write to closed remote file')

            def close(rf):
                if rf._is_open:
                    try:
                        rf._file.close()

                        if not rf._sandboxing:
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

    # =====[ Boolean tests ]====

    def exists(self, filename):
        """
        Returns True when this file exists.
        """
        try:
            self._run_silent_sudo("test -f '%s' || test -d '%s'" % (esc1(filename), esc1(filename)))
            return True
        except ExecCommandFailed:
            return False

    def has_command(self, command):
        """
        Test whether this command can be found in the bash shell, by executing a 'which'
        """
        try:
            self._run_silent("which '%s'" % esc1(command))
            return True
        except ExecCommandFailed:
            return False

    # ====[ Context mangement (Path and environment variables) ]====

    def prefix(self, command):
        """
        Prefix all commands with given command plus ``&&``.

        with host.prefix('workon mvne'):
            host.run('./manage.py migrate')

        Based on Fabric prefix
        """
        class Prefix(object):
            def __enter__(context):
                self._command_prefixes.append(command)

            def __exit__(context, *args):
                self._command_prefixes.pop()
        return Prefix()

    def cd(self, path):
        """
        # Execute commands in this directory.
        # Nesting of cd-statements is allowed.

        with host.cd('~/directory'):
            host.run('ls')
        """
        class CD(object):
            def __enter__(context):
                self._path.append(path)

            def __exit__(context, *args):
                self._path.pop()
        return CD()


    def env(self, variable, value, escape=True):
        """
        Set this environment variable
        """
        if escape:
            value = "'%s'" % esc1(value)

        class ENV(object):
            def __enter__(context):
                self._env.append( (variable, value) )

            def __exit__(context, *args):
                self._env.pop()
        return ENV()

    def sandbox(self, enable=True):
        """
        Context for enable sandboxing on this host.
        No commands will be executed, but syntax will be checked. (through bash -n -c '...')
        """
        class Sandbox(object):
            def __enter__(context):
                context._was_sandbox = self._sandboxing
                self._sandboxing = enable

            def __exit__(context, *args):
                self._sandboxing = context._was_sandbox
        return Sandbox()

    # Some simple wrappers for the commands

    def run(self, pty, command, *args, **kwargs):
        """
        Run this command.
        """
        assert isinstance(command, basestring)
        return self._run(pty, command, *args, **kwargs)


    def sudo(self, pty, command, *args, **kwargs):
        """
        Run this command using sudo.
        """
        kwargs['use_sudo'] = True
        return self.run(pty, command, *args, **kwargs)


class SSHBackend(object):
    """
    Manage Paramiko's SSH connection for a Host.

    When multiple instances of the same SSHHost are created, they will all
    share the same backend (this class). Only one ssh connection per host
    will be created, and shared between all threads.
    """
    def __init__(self, get_host_instance):
        self._get_host_instance = get_host_instance
        self._ssh_cache = None
        self._lock = threading.Lock()

    def __del__(self):
        # Terminate Paramiko's SSH thread
        if self._ssh_cache:
            self._ssh_cache.close()
            self._ssh_cache = None

    @property
    def ssh(self):
        """
        Ssh connection. The actual connection to the host is established
        only after the first call of self._ssh
        """
        # Lock: be sure not to create this connection from several threads at
        # the same time.
        self._lock.acquire()

        if not (self._ssh_cache and self._ssh_cache._transport and self._ssh_cache._transport.is_active()):
            h = self._get_host_instance()

            # Show connecting message (in current stdout)
            sys.stdout.write('*** Connecting to %s (%s)...\n' % (h.address, h.slug))
            sys.stdout.flush()

            # Connect
            self._ssh_cache = paramiko.SSHClient()

            if not h.reject_unknown_hosts:
                self._ssh_cache.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            try:
                if h.key_filename:
                    # When a key filename has been given, use the key
                    self._ssh_cache.connect(h.address, port=h.port, username=h.username, key_filename=h.key_filename, timeout=h.timeout)

                else:
                    # Otherwise, use a password instead
                    self._ssh_cache.connect(h.address, port=h.port, username=h.username, password=h.password, timeout=h.timeout)

            except (paramiko.SSHException, Exception) as e:
                self._ssh_cache = None
                raise Exception('Could not connect to host %s (%s)\n%s' % (h.slug, h.address, unicode(e)))

        # Release lock
        self._lock.release()

        return self._ssh_cache


class SSHHost(Host):
    """
    SSH Host
    """
    # Base host configuration
    reject_unknown_hosts = False
    key_filename = None
    address = 'example.com'
    username = 'someone'
    port = 22
    timeout = 10 # Seconds
    keepalive_interval  = 30

    def __init__(self, backend=None):
        Host.__init__(self)
        self._backend = backend or SSHBackend(lambda: self)

    def clone(self):
        """
        Return a new Host() instance, as a copy of this state.
        (Every thread has its own state of every host.)
        """
        # Create a new instance of this class, but reuse the same SSH Backend.
        new_host = self.__class__(backend=self._backend)
        self._copy_state_to(new_host)
        return new_host

    def _get_session(self):
        transport = self._backend.ssh.get_transport()
        transport.set_keepalive(self.keepalive_interval)
        chan = transport.open_session()
        return chan

    @property
    def sftp(self):
        transport = self._backend.ssh.get_transport()
        transport.set_keepalive(self.keepalive_interval)
        return paramiko.SFTPClient.from_transport(transport)

    def expand_path(self, path):
        # Tilde expansion
        if path.startswith('~'):
            home = self.sftp.normalize('.')
            path = path.replace('~', home, 1)

        # Expand remote path, using the cwd
        if not os.path.isabs(path):
            path = os.path.join(self.cwd, path)

        return path

    def start_interactive_shell(self, pty, command=None, logger=None, initial_input=None):
        """
        Start /bin/bash and redirect all SSH I/O from stdin and to stdout.
        """
        logger = logger or self.dummy_logger

        # Start a new shell using the same dimentions as the current terminal
        height, width = pty.get_size()
        chan = self._backend.ssh.invoke_shell(term=self.term, height=height, width=width)

        # Keep size of local pty and remote pty in sync
        def set_size():
            height, width = pty.get_size()
            chan.resize_pty(width=width, height=height)
        pty.set_ssh_channel_size = set_size

        # Start logger
        with logger.log_run(self, command=command, shell=True, sandboxing=self._sandboxing) as log_entry:
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


class LocalHostBackend(object):
    """
    The backend for LocalHost, is just a password store.
    Just to make sure that the password doesn't have to be asked again
    for every new clone of LocalHost. (In every thread.)
    """
    def __init__(self):
        self.password = None


class LocalHost(Host):
    slug = 'localhost'
    address = 'localhost'

    def __init__(self, backend=None):
        Host.__init__(self)
        self._backend = backend or LocalHostBackend()

    def _run(self, *a, **kw):
        if kw.get('use_sudo', False):
            self._ensure_password_is_known()
        return Host._run(self, *a, **kw)

    def clone(self):
        # Clone state of this host into a new Host instance.
        new_host = self.__class__(backend=self._backend)
        self._copy_state_to(new_host)
        return new_host

    def expand_path(self, path):
        return os.path.expanduser(path)

    def _ensure_password_is_known(self):
        # Make sure that we know the localhost password, before running sudo.
        tries = 0
        while not self._backend.password:
            self._backend.password = read_input('[sudo] password for %s at %s' % (self.username, self.slug), True)

            # Check password
            try:
                Host._run_silent_sudo(self, '/bin/true')
            except ExecCommandFailed:
                print 'Incorrect password'
                self._backend.password = None

                tries += 1
                if tries >= 3:
                    raise Exception('Incorrect password')

    @property
    def password(self):
        return self._backend.password

    @property
    def username(self):
        return getpass.getuser()

    def get_ip_address(self, interface='eth0'):
        # Just return '127.0.0.1'. Laptops are often only connected
        # on wlan0, and looking for eth0 would return an empty string.
        return '127.0.0.1'

    def _get_session(self):
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

    @property
    def sftp(self):
        """
        (For Localhost)
        Compatibility with Paramiko's SFTPClient.from_transport
        """
        import __builtin__
        class LocalhostFTP(object):
            open = __builtin__.open

            def normalize(self, path):
                return os.path.realpath(path)

        return LocalhostFTP()

    def start_interactive_shell(self, pty, command=None, logger=None, initial_input=None):
        self._run(pty, command='/bin/bash', logger=logger, initial_input=initial_input)
