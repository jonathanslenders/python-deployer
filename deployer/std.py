import sys
import threading
import termios
import tty


class TeeStd(object):
    """
    Like the unix 'tee' command.
    Wrapper around an std object, which allows other handlers to listen
    along.
    """
    _names = ('_std', '_read_listeners', 'add_read_listener', 'remove_read_listener', 'read')

    def __init__(self, std):
        self._std = std
        self._read_listeners = []

    def add_read_listener(self, handler):
        self._read_listeners.append(handler)

    def remove_read_listener(self, handler):
        self._read_listeners.remove(handler)

    def read(self, *a):
        data = self._std.read(*a)

        for l in self._read_listeners:
            l(data)

        return data

    def __getattribute__(self, name):
        if name in TeeStd._names:
            return object.__getattribute__(self, name)
        else:
            return getattr(self._std, name)

    def __setattr__(self, name, value):
        if name in TeeStd._names:
            object.__setattr__(self, name, value)
        else:
            setattr(self._std, name, value)


class Std(object):
    """
    Threading aware proxy for sys.stdin/sys.stdout
    This will make sure that print statements are automatically routed to the
    correct pseudo terminal.
    This is the only one that should be used in the whole deployer framework.
    """
    def __init__(self, fallback, mode):
        # `fallback` is the default fallback, in case none has been set for
        # the current thread.
        self._f = { }
        self._fallback = fallback

    def get_handler(self):
        t = threading.currentThread()
        return self._f.get(t, self._fallback)

    def set_handler(self, value):
        t = threading.currentThread()
        self._f[t] = value

    def del_handler(self):
        t = threading.currentThread()
        del self._f[t]

    def __getattribute__(self, name):
        """
        Route all attribute lookups to the stdin/out object
        that belongs to the current thread.
        """
        if name in ('__init__', 'get_handler', 'set_handler', 'del_handler',
                '__getattribute__', '__eq__', '__setattr__', '_f', '_fallback'):
            return object.__getattribute__(self, name)
        else:
            return getattr(self.get_handler(), name)

    def __eq__(self, value):
        return self.get_handler() == value

    def __setattr__(self, name, value):
        """
        Redirect setting of attribute to the thread's std.
        """
        if name in ('_f', '_fallback'):
            object.__setattr__(self, name, value)
        else:
            setattr(self.get_handler(), name, value)


has_been_setup = False

def setup():
    """
    Make sure that sys.stdin and sys.stdout are replaced by an Std object.
    """
    global has_been_setup
    if not has_been_setup:
        has_been_setup = True
        sys.stdin = Std(sys.__stdin__, 'r')
        sys.stdout = Std(sys.__stdout__, 'w')


class raw_mode(object):
    """
    with raw_mode(stdin):
        ''' the pseudo-terminal stdin is now used in raw mode '''
    """
    def __init__(self, stdin):
        self.stdin = stdin

        if self.stdin.isatty():
            self.attrs_before = termios.tcgetattr(self.stdin)

    def __enter__(self):
        if self.stdin.isatty():
            # NOTE: On os X systems, using pty.setraw() fails. Therefor we are using this:
            newattr = termios.tcgetattr(self.stdin.fileno())
            newattr[tty.LFLAG] = newattr[tty.LFLAG] & ~(termios.ECHO | termios.ICANON | termios.IEXTEN | termios.ISIG)
            termios.tcsetattr(self.stdin.fileno(), termios.TCSANOW, newattr)

    def __exit__(self, *a, **kw):
        if self.stdin.isatty():
            termios.tcsetattr(self.stdin.fileno(), termios.TCSANOW, self.attrs_before)
