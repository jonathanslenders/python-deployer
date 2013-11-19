from deployer.cli import CLInterface, Handler, HandlerType
from deployer.console import Console
from deployer.host import Host
from deployer.host import LocalHost
from deployer.utils import esc1
from termcolor import colored

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

class DirectoryType(HandlerType):
    color = 'blue'

class FileType(HandlerType):
    color = None


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
        with console.progress_bar('Reading directory...', clear_on_finish=True):
            cwd = self.getcwd()
            for s in self.listdir_stat():
                self._stat_cache[(cwd, s.filename)] = s

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

            @property
            def handler_type(self):
                host = get_host_func(self.shell)
                if self.path in ('..', '.', '/') or host.stat(self.path).is_dir:
                    return DirectoryType()
                else:
                    return FileType()

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
                host = get_host_func(self.shell)

                # First check whether this name appears in the current directory.
                # (avoids stat calls on unknown files.)
                if name in host.listdir():
                    # When this file does not exist, return
                    try:
                        s = host.stat(name)
                        if (files_only and not s.is_file):
                            return
                        if (directories_only and not s.is_dir):
                            return
                    except IOError: # stat on non-existing file.
                        return
                    finally:
                        return ChildHandler(self.shell, name)

                # Root, current and parent directory.
                if name in ('/', '..', '.') and not files_only:
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
        self.shell.host.start_interactive_shell(initial_input=initial_input)


class Lconnect(SCPHandler):
    is_leaf = True
    handler_type = LocalType()

    def __call__(self): # XXX: code duplication of deployer/shell.py
        initial_input = "cd '%s'\n" % esc1(self.shell.localhost.getcwd())
        self.shell.localhost.start_interactive_shell(initial_input=initial_input)


@remote_handler(files_only=True)
def view(shell, path):
    """ View remote file. """
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
    shell.host.run("vim '%s'" % esc1(path))

class Pwd(SCPHandler):
    """ Display remote working directory. """
    is_leaf = True
    handler_type = RemoteType()

    def __call__(self):
        print self.shell.host.getcwd()

def make_ls_handler(handler_type_, get_host_func):
    """ Make a function that does a directory listing """
    class Ls(SCPHandler):
        is_leaf = True
        handler_type = handler_type_()

        def __call__(self):
            host = get_host_func(self.shell)
            files = host.listdir()

            def iterator():
                for f in files:
                    if host.stat(f).is_dir:
                        yield colored(f, DirectoryType.color), len(f)
                    else:
                        yield f, len(f)

            console = Console(self.shell.pty)
            console.lesspipe(console.in_columns(iterator()))
    return Ls

ls = make_ls_handler(RemoteType, lambda shell: shell.host)
lls = make_ls_handler(LocalType, lambda shell: shell.localhost)


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
def lview(shell, path):
    """ View local file. """
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
    h.put_file(os.path.join(shell.localhost.getcwd(), filename), filename)


@remote_handler(files_only=True)
def get(shell, filename):
    """ Retrieve the remote-path and store it on the local machine """
    target = os.path.join(shell.localhost.getcwd(), filename)
    print 'Downloading %s to %s...' % (filename, target)
    h = shell.host
    h.get_file(filename, target)


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
    shell.localhost.run("vim '%s'" % esc1(path))


class RootHandler(SCPHandler):
    subhandlers = {
            'clear': Clear,
            'exit': Exit,

            'ls': ls,
            'cd': cd,
            'pwd': Pwd,
            'stat': stat_handler,
            'view': view,
            'edit': edit,
            'connect': Connect,

            'lls': lls,
            'lcd': lcd,
            'lpwd': Lpwd,
            'lstat': lstat,
            'lview': lview,
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
        assert pty

        self.host = type('RemoteSCPHost', (CacheMixin, host), { })(pty=pty, logger=logger_interface)
        self.host.fill_cache(pty)
        self.localhost = LocalHost(pty=pty, logger=logger_interface)
        self.localhost.host_context._chdir(os.getcwd())
        self.pty = pty
        self.root_handler = RootHandler(self)

        CLInterface.__init__(self, self.pty, RootHandler(self))

        # Caching for autocompletion (directory -> list of content.)
        self._cd_cache = { }

    @property
    def prompt(self):
        get_name = lambda p: os.path.split(p)[-1]

        return [
                    ('local:%s' % get_name(self.localhost.getcwd() or ''), 'yellow'),
                    (' ~ ', 'cyan'),
                    ('%s:' % self.host.slug, 'yellow'),
                    (get_name(self.host.getcwd() or ''), 'yellow'),
                    (' > ', 'cyan'),
                ]
