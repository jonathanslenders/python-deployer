import array
import fcntl
import os
import select as _select
import sys
import termios


class Pty(object):
    """
    Group stdin/stdout as a terminal instance.

    Contains helper function, for opening an additional Pty,
    if parallel deployments are supported.
    """
    def __init__(self, stdin=None, stdout=None):
        self.stdin = stdin or sys.__stdin__
        self.stdout = stdout or sys.__stdout__
        self.set_ssh_channel_size = None

    def get_size(self):
        # Thanks to fabric (fabfile.org), and
        # http://sqizit.bartletts.id.au/2011/02/14/pseudo-terminals-in-python/
        """
        Get the rows/cols for this pty
        """
        if self.stdout.isatty():
            # Buffer for the C call
            buf = array.array('h', [0, 0, 0, 0 ])

            # Do TIOCGWINSZ (Get)
            fcntl.ioctl(self.stdout.fileno(), termios.TIOCGWINSZ, buf, True)

            # Return rows, cols
            return buf[0], buf[1]
        else:
            # Default value
            return 24, 80

    def set_size(self, rows, cols):
        if self.stdout.isatty():
            # Buffer for the C call
            buf = array.array('h', [rows, cols, 0, 0 ])

            # Do: TIOCSWINSZ (Set)
            fcntl.ioctl(self.stdout.fileno(), termios.TIOCSWINSZ, buf)

            self.trigger_resize()

    def trigger_resize(self):
        # Call size setter for SSH channel
        if self.set_ssh_channel_size:
            self.set_ssh_channel_size()

    @property
    def auxiliary_ptys_are_available(self):
        # Override this when secondary pty's are available.
        return False

    def run_in_auxiliary_ptys(self, callbacks):
        """
        Open an additional terminal, and call this function with the
        new 'pty' as parameter. The callback can run in another thread.
        """
        from deployer.console import warning
        warning('Can not open auxiliary pseudo terminal. Running commands in here.') # TODO: Maybe rather info, than warning

        # This should be overriden by other PTY objects, for environments
        # which support parallellism.

        class ForkResult(object):
            def __init__(s):
                # The callbacks parameter can be either a single callable, or a list
                if callable(callbacks):
                    s.result = callbacks(self)
                else:
                    s.result = [ c(self) for c in callbacks ]

            def join(s):
                pass # Wait for the thread to finish. No thread here.

        return ForkResult()


class DummyPty(Pty):
    def __init__(self):
        Pty.__init__(self, open('/dev/null', 'r'), open('/dev/null', 'r'))

    def pty_size(self):
        return (40, 80)


# Alternative pty_size implementation. (Will spawn a child process, so less
# efficient.)
def _pty_size(self):
    """
    Returns (height, width)
    """
    height, width = os.popen('stty size', 'r').read().split()
    return int(height), int(width)


def select(*args, **kwargs):
    """
    This is a wrapper around select.select.
    When the SIGWINCH signal is handled, other system calls, like select
    are aborted in Python. This wrapper will retry the system call.

    >>  signal.signal(signal.SIGWINCH, sigwinch_handler)
    """
    from _socket import error as SocketError
    import errno

    while True:
        try:
            return _select.select(*args, **kwargs)
        except Exception as e:
            # Retry select call when EINTR
            if e.args and e.args[0] == errno.EINTR:
                continue
            else:
                raise
