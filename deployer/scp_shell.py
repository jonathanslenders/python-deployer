from deployer.cli import CLInterface, Handler, HandlerType
from deployer.console import Console
from deployer.host import Host
from deployer.host import LocalHost
from deployer.utils import esc1

import sys
import os
import stat
import os.path

# Types

class BuiltinType(HandlerType):
    color = 'cyan'

class LocalType(HandlerType):
    color = 'green'

class RemoteType(HandlerType):
    color = 'yellow'

class ModifyType(HandlerType):
    color = 'red'


class CacheMixin(object):
    """
    Mixin for Host, which adds caching to listdir and stat.
    (This makes autocompletion much faster.
    """
    def __init__(self, *a, **kw):
        super(CacheMixin, self).__init__(*a, **kw)
        self._listdir_cache = {}
        self._stat_cache = {}

    def listdir(self):
        cwd = self.getcwd()
        if cwd not in self._listdir_cache:
            self._listdir_cache[cwd] = super(CacheMixin, self).listdir()
        return self._listdir_cache[cwd]

    def stat(self, path):
        cwd = self.getcwd()
        if (cwd, path) not in self._stat_cache:
            self._stat_cache[(cwd, path)] = super(CacheMixin, self).stat(path)
        return self._stat_cache[(cwd, path)]

    def fill_cache(self, pty):
        """ Fill cache for current directory. """
        console = Console(pty)
        with console.progress_bar('Reading directory...', clear_on_finish=True) as p:
            # Loop through all the files, and call 'stat'
            content = self.listdir()
            p.expected = len(content)

            for f in content:
                p.next()
                self.stat(f)

# Handlers

class SCPHandler(Handler):
    def __init__(self, shell):
        self.shell = shell

def remote_handler(files_only=False, directories_only=False):
    """ Create a node system that does autocompletion on the remote path. """
    return _create_autocompleter_system(files_only, directories_only, RemoteType,
            lambda shell: shell.host)


def local_handler(files_only=False, directories_only=False):
    """ Create a node system that does autocompletion on the local path. """
    return _create_autocompleter_system(files_only, directories_only, LocalType,
            lambda shell: shell.localhost)


def _create_autocompleter_system(files_only, directories_only, handler_type_cls, get_host_func):
    def local_handler(func):
        class ChildHandler(SCPHandler):
            is_leaf = True

            def __init__(self, shell, path):
                self.path = path
                SCPHandler.__init__(self, shell)

            def __call__(self):
                func(self.shell, self.path)

        class MainHandler(SCPHandler):
            handler_type = handler_type_cls()

            def complete_subhandlers(self, part):
                host = get_host_func(self.shell)
                # Progress bar.
                for f in host.listdir():
                    if f.startswith(part):
                        if files_only and not host.stat(f).is_file:
                            continue
                        if directories_only and not host.stat(f).is_dir:
                            continue

                        yield f, ChildHandler(self.shell, f)

                # Root directory.
                if '/'.startswith(part) and not files_only:
                    yield f, ChildHandler(self.shell, '/')

            def get_subhandler(self, name):
                return ChildHandler(self.shell, name)

        return MainHandler
    return local_handler


class Clear(SCPHandler):
    """ Clear window.  """
    is_leaf = True
    handler_type = BuiltinType()

    def __call__(self):
        sys.stdout.write('\033[2J\033[0;0H')
        sys.stdout.flush()

class Exit(SCPHandler):
    """ Quit the SFTP shell. """
    is_leaf = True
    handler_type = BuiltinType()

    def __call__(self):
        self.shell.exit()


class Connect(SCPHandler):
    is_leaf = True
    handler_type = RemoteType()

    def __call__(self): # XXX: code duplication of deployer/shell.py
        initial_input = "cd '%s'\n" % esc1(self.shell.host.getcwd())
        self.shell.host.start_interactive_shell(self.shell.pty, initial_input=initial_input)


class Lconnect(SCPHandler):
    is_leaf = True
    handler_type = LocalType()

    def __call__(self): # XXX: code duplication of deployer/shell.py
        initial_input = "cd '%s'\n" % esc1(self.shell.localhost.getcwd())
        self.shell.localhost.start_interactive_shell(self.shell.pty, initial_input=initial_input)


@remote_handler(files_only=True)
def display(shell, path):
    """ Display remote file. """
    console = Console(shell.pty)

    with shell.host.open(path, 'r') as f:
        def reader():
            while True:
                line = f.readline()
                if line:
                    yield line.rstrip('\n')
                else:
                    return # EOF

        console.lesspipe(reader())

@remote_handler(files_only=True)
def edit(shell, path):
    """ Edit file in editor. """
    shell.host.run(shell.pty, "vim '%s'" % esc1(path))

class Pwd(SCPHandler):
    """ Display remote working directory. """
    is_leaf = True
    handler_type = RemoteType()

    def __call__(self):
        print self.shell.host.getcwd()


class Ls(SCPHandler):
    """ Display a remote directory listing """
    is_leaf = True
    handler_type = RemoteType()

    def __call__(self):
        files = self.shell.host.listdir()
        console = Console(self.shell.pty)
        console.lesspipe(console.in_columns(files))


@remote_handler(directories_only=True)
def cd(shell, path):
    shell.host.host_context._chdir(path)
    print shell.host.getcwd()
    shell.host.fill_cache(shell.pty)


@local_handler(directories_only=True)
def lcd(shell, path):
    shell.localhost.host_context._chdir(path)
    print shell.localhost.getcwd()


class Lls(SCPHandler):
    """ Display local directory listing  """
    handler_type = LocalType()
    is_leaf = True

    def __call__(self):
        files = self.shell.localhost.listdir()
        console = Console(self.shell.pty)
        console.lesspipe(console.in_columns(files))


class Lpwd(SCPHandler):
    """ Print local working directory. """
    handler_type = LocalType()
    is_leaf = True

    def __call__(self):
        print self.shell.localhost.getcwd()


@local_handler(files_only=True)
def ldisplay(shell, path):
    """ Display local file. """
    console = Console(shell.pty)

    with shell.localhost.open(path, 'r') as f:
        def reader():
            while True:
                line = f.readline()
                if line:
                    yield line.rstrip('\n')
                else:
                    return # EOF

        console.lesspipe(reader())

@local_handler(files_only=True)
def put(shell, filename):
    """ Upload local-path and store it on the remote machine. """
    print 'Uploading %s...', filename
    h = shell.host
    h.put_file(os.path.join(shell.localhost.getcwd(), filename),
            filename, logger=shell.logger_interface)


@remote_handler(files_only=True)
def get(shell, filename):
    """ Retrieve the remote-path and store it on the local machine """
    target = os.path.join(shell.localhost.getcwd(), filename)
    print 'Downloading %s to %s...' % (filename, target)
    h = shell.host
    h.get_file(filename, target, logger=shell.logger_interface)


@remote_handler()
def stat_handler(shell, filename):
    """ Print stat information of this file. """
    s = shell.host.stat(filename)

    print ' Is file:      %r' % s.is_file
    print ' Is directory: %r' % s.is_dir
    print
    print ' Size:         %r bytes' % s.st_size
    print
    print ' st_uid:       %r' % s.st_uid
    print ' st_gid:       %r' % s.st_gid
    print ' st_mode:      %r' % s.st_mode


@local_handler()
def lstat(shell, filename):
    """ Print stat information for this local file. """
    s =  shell.localhost.stat(filename)

    print ' Is file:      %r' % stat.S_ISREG(s.st_mode)
    print ' Is directory: %r' % stat.S_ISDIR(s.st_mode)
    print
    print ' Size:         %r bytes' % int(s.st_size)
    print
    print ' st_uid:       %r' % s.st_uid
    print ' st_gid:       %r' % s.st_gid
    print ' st_mode:      %r' % s.st_mode

@local_handler(files_only=True)
def ledit(shell, path):
    """ Edit file in editor. """
    shell.localhost.run(shell.pty, "vim '%s'" % esc1(path))


class RootHandler(SCPHandler):
    subhandlers = {
            'clear': Clear,
            'exit': Exit,

            'ls': Ls,
            'cd': cd,
            'pwd': Pwd,
            'stat': stat_handler,
            'display': display,
            'edit': edit,
            'connect': Connect,

            'lls': Lls,
            'lcd': lcd,
            'lpwd': Lpwd,
            'lstat': lstat,
            'ldisplay': ldisplay,
            'ledit': ledit,
            'lconnect': Lconnect,

            'put': put,
            'get': get,
    }

    def complete_subhandlers(self, part):
        # Built-ins
        for name, h in self.subhandlers.items():
            if name.startswith(part):
                yield name, h(self.shell)

    def get_subhandler(self, name):
        if name in self.subhandlers:
            return self.subhandlers[name](self.shell)



class Shell(CLInterface):
    """
    Interactive secure copy shell.
    """
    def __init__(self, pty, host, logger_interface, clone_shell=None): # XXX: import clone_shell
        assert issubclass(host, Host)

        self.host = type('RemoteSCPHost', (CacheMixin, host), { })()
        self.host.fill_cache(pty)
        self.localhost = LocalHost()
        self.localhost.host_context._chdir(os.getcwd())
        self.logger_interface = logger_interface
        self.pty = pty
        self.root_handler = RootHandler(self)

        CLInterface.__init__(self, self.pty, RootHandler(self))

        # Caching for autocompletion (directory -> list of content.)
        self._cd_cache = { }

    @property
    def prompt(self):
        get_name = lambda p: os.path.split(p)[-1]

        return [
                    ('local:%s' % get_name(os.getcwd()), 'yellow'),
                    (' ~ ', 'cyan'),
                    ('%s:' % self.host.slug, 'yellow'),
                    (get_name(self.host.getcwd() or ''), 'yellow'),
                    (' > ', 'cyan'),
                ]
