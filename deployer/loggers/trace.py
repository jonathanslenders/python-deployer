from deployer.loggers import Logger, RunCallback, FileCallback, ForkCallback, Actions
from deployer.utils import indent
import termcolor


class TraceLogger(Logger):
    """
    Log traces inside this class
    For reflextion code.

    After execution, we can retrieve a list of Actions/Groups.
    (where every group can consist of other Actions/Groups.
    """
    def __init__(self):
        self.trace = TraceGroup('root')
        self._group_stack = [ self.trace ]

    @property
    def traces(self):
        return self.trace.items

    @property
    def first_trace(self):
        return self.trace.items[0]

    def enter_group(self, func_name, *args, **kwargs):
        # Nest new group
        new_group = TraceGroup(func_name, *args, **kwargs)

        self._group_stack[-1].items.append(new_group)
        self._group_stack.append(new_group) # Become the new list head.

    def leave_group(self):
        self._group_stack.pop()

    def log_fork(self, fork_entry):
        new_group = TraceFork(fork_entry)
        self._group_stack[-1].items.append(new_group)

        class callback(ForkCallback):
            def get_fork_logger(c):
                logger = TraceLogger()
                logger._group_stack = [ new_group ]
                return logger

            def completed(self):
                new_group.completed = True

        return callback()

    def log_run(self, run_entry):
        self._group_stack[-1].items.append(run_entry)
        return RunCallback()

    def log_file_opened(self, file_entry):
        self._group_stack[-1].items.append(file_entry)
        return FileCallback()


class TraceGroup(object):
    """
    Data structure where a trace log is stored.
    """
    def __init__(self, func_name, *args, **kwargs):
        self.items = []
        self.func_name = func_name
        self.args = args
        self.kwargs = kwargs

    @property
    def all_io(self):
        for item in self.items:
            if isinstance(item, TraceGroup):
                for io in item.all_io:
                    yield io
            elif item.entry_type == Actions.Run:
                yield item.io

class TraceFork(object):
    def __init__(self, fork_entry):
        self.fork_entry = fork_entry
        self.items = []
        self.completed = False

class TracePrinter(object):
    """
    Printer for outputting the trace structure as string.
    (optionally colored)
    """
    property_color = 'green'
    property_color_attrs = ['dark']
    func_color = 'green'
    func_color_attrs = ['bold']
    call_color = 'red'
    call_color_attrs = []
    key_color = 'yellow'
    key_color_attrs = []
    param_color = 'blue'
    param_color_attrs = []

    def __init__(self, trace):
        self.trace = trace

    def _wrap(self, string, outputtype):
        color = getattr(self, outputtype + '_color', 'default')
        attrs = getattr(self, outputtype + '_color_attrs', [])
        return termcolor.colored(string, color, attrs=attrs)

    def print_color(self):
        if '.property' in self.trace.func_name:
            f = lambda string: self._wrap(string, 'property')
        else:
            f = lambda string: self._wrap(string, 'func')

        params = ', '.join(map(repr, self.trace.args) +
                            [ '%s=%s' % (k, repr(v)) for k,v in self.trace.kwargs.items() ])
        if self.trace.items:
            return (f('%s(%s)\n[\n' % (self.trace.func_name, params)) +
                    ''.join([ indent(self._print_item_color(i), prefix='  ') for i in self.trace.items ]) +
                    f(']'))
        else:
            return f('%s(%s)' % (self.trace.func_name, params))

    def _print_item_color(self, item):
        c = lambda string: self._wrap(string, 'call')
        k = lambda string: self._wrap(string, 'key')
        p = lambda string: self._wrap(string, 'param')


        if isinstance(item, TraceGroup):
            return TracePrinter(item).print_color()

        elif isinstance(item, TraceFork):
            return (
                    c(u'fork') +
                    k(u'(') + p(item.fork_name) + k(u') {\n') +
                    TracePrinter(item).print_color() +
                    k(u'\n}'))
        elif item.entry_type == Actions.Run:
            return (
                    c(u'sandbox' if item.sandboxing else u'run') +
                    k(u'{\n host: ') + p(item.host.slug) +
                    k(u',\n sudo: ') + p(str(item.use_sudo)) +
                    k(u',\n command: ') + p(item.command) +
                    k(u',\n status_code: ') + p(item.status_code) +
                    k(u'\n}'))

        elif item.entry_type == Actions.Open:
            return (
                    c('open') +
                    k(u'{\n host: ') + p(item.host.slug) +
                    k(u',\n sudo: ') + p(item.use_sudo) +
                    k(u',\n mode: ') + p(item.mode) +
                    k(u',\n remote: ') + p(item.remote_path) +
                    k(u',\n succeeded: ') + p(item.succeeded) +
                    k(u'\n}'))
