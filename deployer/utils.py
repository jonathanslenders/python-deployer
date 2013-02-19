import sys
from deployer import std


def esc2(string):
    """
    Escape double quotes
    """
    return string.replace('"', r'\"')


def esc1(string):
    """
    Escape single quotes

    If you want to get "Here's some text", it can be quoted as
    'Here'\''s some text' So, we have to lease the single quoted string, add
    an escaped quote, and enter the single quoted string again.
    """
    return string.replace("'", r"'\''")


def indent(string, prefix='    '):
    """
    Indent every line of this string.
    """
    return ''.join('%s%s\n' % (prefix, s) for s in string.split('\n'))


class capture(object):
    """
    Context manager for capturing stdout.
    """
    def __init__(self, copy_to_original_stdout=True):
        self.copy_to_original_stdout = copy_to_original_stdout
        std.setup()

    def __enter__(self):
        # Replace stdout by capture object
        self.original_stdout = sys.stdout.get_handler()
        self._content = []

        class Capture(object):
            def write(_, content):
                self._content.append(content)

                if self.copy_to_original_stdout:
                    self.original_stdout.write(content)

            def flush(_):
                return self.original_stdout.flush()

            def isatty(_):
                return self.original_stdout.isatty()

            def fileno(_):
                return self.original_stdout.fileno()


        sys.stdout.set_handler(Capture())
        return self

    @property
    def value(self):
        """
        Retrieve captured content.
        """
        return ''.join(self._content)

    def __exit__(self, *a):
        # Restore stdout
        sys.stdout.set_handler(self.original_stdout)

def map_reduce_services(services, map_method, reduce_function=list.append, collector=[], recursive=True, **kwargs):
    """
    Iterate over services, call a method and group the results.

    Iterate over the given services (and, if requested, sub services and
    further). For each service, if the given map_method exists, call it. Group
    the results by passing them to reduce_function, which will operator on the
    given collector and the new results.

    Example usage:

    map_reduce_services(self.parent, map_method='get_uwsgi_config', reduce_function=dict.update, collector={}, host=self.host)
    """
    services = services[:]
    s_idx = 0
    while s_idx < len(services):
        s = services[s_idx]
        if hasattr(s, map_method):
            for result in getattr(s, map_method)(**kwargs):
                reduce_function(collector, result)
        if recursive:
            for name, subservice in s.get_subservices(include_isolations=False):
                if name != 'root' and subservice not in services:
                    services.append(subservice)
        s_idx += 1

    return collector
