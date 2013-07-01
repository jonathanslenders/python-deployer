from deployer.cli import CLInterface, Handler, HandlerType
from deployer.console import Console
from deployer.console import NoInput
from deployer.inspection import Inspector, PathType
from deployer.node import ActionException, Env, IsolationIdentifierType

from inspect import getfile
from itertools import groupby

from pygments import highlight
from pygments.formatters import TerminalFormatter
from pygments.lexers import PythonLexer, PythonTracebackLexer

import deployer
import inspect
import socket
import sys
import termcolor
import traceback

__all__ = ('Shell', )


# Handler types

class ActionType(HandlerType):
    def __init__(self, color):
        self.color = color
        self.postfix = '*'

def type_of_node(node):
    group = Inspector(node).get_group()
    return NodeType(group.color)

def type_of_action(action):
    group = action.node_group
    return ActionType(group.color)

class NodeType(HandlerType):
    def __init__(self, color):
        self.color = color

class BuiltinType(HandlerType):
    color = 'cyan'


# Utils for navigation

def find_root_node(node):
    while node.parent:
        node = node.parent
    return node


def create_navigable_handler(call_handler):
    """
    Crete a ShellHandler which has node path completion.
    """
    class PathHandler(ShellHandler):
        is_leaf = True

        @property
        def handler_type(self):
            return type_of_node(self.node)

        def __init__(self, shell, node):
            ShellHandler.__init__(self, shell)
            self.node = node

        def get_subhandler(self, name):
            parent = self.node.parent

            if name == '.':
                return self

            if name == '-' and self.shell.state.can_cdback:
                return PathHandler(self.shell, self.shell.state.previous_node)

            if parent and name == '/':
                root = find_root_node(parent)
                return PathHandler(self.shell, root)

            if parent and name == '..':
                return PathHandler(self.shell, parent)

            elif name.startswith(':'):
                ids = tuple(name[1:].split(':'))
                try:
                    return PathHandler(self.shell, Inspector(self.node).get_isolation(ids, IsolationIdentifierType.HOSTS_SLUG))
                except AttributeError:
                    pass

            for c in Inspector(self.node).get_childnodes(include_private=True):
                if Inspector(c).get_name() == name:
                    return PathHandler(self.shell, c)

        def complete_subhandlers(self, part):
            parent = self.node.parent

            if '.'.startswith(part):
                yield '.', self

            if '-'.startswith(part) and self.shell.state.can_cdback:
                yield '-', PathHandler(self.shell, self.shell.state.previous_node)

            if parent and '/'.startswith(part):
                root = find_root_node(parent)
                yield '/', PathHandler(self.shell, root)

            if parent and '..'.startswith(part):
                yield ('..', PathHandler(self.shell, parent))

            for i, n in Inspector(self.node).iter_isolations(IsolationIdentifierType.HOSTS_SLUG):
                # Prefix all isolations with colons.
                name = ':%s' % ':'.join(i)
                if name.startswith(part):
                    yield name, PathHandler(self.shell, n)

            # Note: when an underscore has been typed, include private too.
            include_private = part.startswith('_')
            for c in Inspector(self.node).get_childnodes(include_private=include_private):
                name = Inspector(c).get_name()
                if name.startswith(part):
                    yield name, PathHandler(self.shell, c)

        __call__ = call_handler

    class RootHandler(PathHandler):
        handler_type = BuiltinType()

        def __init__(self, shell):
            PathHandler.__init__(self, shell, shell.state._node)

    return RootHandler

# Handlers

class ShellHandler(Handler):
    def __init__(self, shell):
        self.shell = shell


class GroupHandler(ShellHandler):
    """
    Contains a static group of subhandlers.
    """
    subhandlers = { }

    def complete_subhandlers(self, part):
        for name, h in self.subhandlers.items():
            if name.startswith(part):
                yield name, h(self.shell)

    def get_subhandler(self, name):
        if name in self.subhandlers:
            return self.subhandlers[name](self.shell)


class Version(ShellHandler):
    is_leaf = True
    handler_type = BuiltinType()

    def __call__(self):
        print termcolor.colored('  deployer library, version: ', 'cyan'),
        print termcolor.colored(deployer.__version__, 'red')
        print termcolor.colored('  Host:                      ', 'cyan'),
        print termcolor.colored(socket.gethostname(), 'red')
        print termcolor.colored('  Root node class:        ', 'cyan'),
        print termcolor.colored(self.shell.root_node.__module__, 'red'),
        print termcolor.colored('  <%s>' % self.shell.root_node.__class__.__name__, 'red')


@create_navigable_handler
def Connect(self):
    """
    Open interactive SSH connection with this host.
    """
    from deployer.contrib.nodes import connect
    from deployer.host_container import HostsContainer

    class Connect(connect.Connect):
        class Hosts:
            host = self.node.hosts._all

    env = Env(Connect(), pty=self.shell.pty)

    # Run as any other action. (Nice exception handling, e.g. in case of NoInput on host selection.)
    Action(Connect(), 'with_host', self.shell, False).__call__()


@create_navigable_handler
def Find(self):
    def _list_nested_nodes(node, prefix):
        for a in Inspector(node).get_actions():
            yield '%s %s' % (prefix, termcolor.colored(a.name, Inspector(a.node).get_group().color))

        for c in Inspector(node).get_childnodes():
            # Check the parent, to avoid loops.
            if c.parent == node:
                name = Inspector(c).get_name()
                for i in _list_nested_nodes(c, '%s %s' % (prefix, termcolor.colored(name, Inspector(c).get_group().color))):
                    yield i

    Console(self.shell.pty).lesspipe(_list_nested_nodes(self.node, ''))


@create_navigable_handler
def Inspect(self):
    """
    Inspection of the current node. Show host mappings and other information.
    """
    console = Console(self.shell.pty)

    def inspect():
        # Print full name
        yield termcolor.colored('  Node:    ', 'cyan') + \
              termcolor.colored(Inspector(self.node).get_full_name(), 'yellow')

        # Print mro
        yield termcolor.colored('  Mro:', 'cyan')
        i = 1
        for m in self.node.__class__.__mro__:
            if m.__module__ != 'deployer.node' and m != object:
                yield termcolor.colored('              %i ' % i, 'cyan') + \
                      termcolor.colored('%s.' % m.__module__, 'red') + \
                      termcolor.colored('%s' % m.__name__, 'yellow')
                i += 1

        # File names
        yield termcolor.colored('  Files:', 'cyan')
        i = 1
        for m in self.node.__class__.__mro__:
            if m.__module__ != 'deployer.node' and m != object:
                yield termcolor.colored('              %i ' % i, 'cyan') + \
                      termcolor.colored(getfile(m), 'red')
                i += 1

        # Print host mappings
        yield termcolor.colored('  Hosts:', 'cyan')

        for role in sorted(self.node.hosts._hosts.keys()):
            items = self.node.hosts._hosts[role]
            yield termcolor.colored('         "%s"' % role, 'yellow')
            i = 1
            for host in sorted(items, key=lambda h:h.slug):
                yield termcolor.colored('            %3i ' % i, 'cyan') + \
                      termcolor.colored('%-25s (%s)' % (host.slug, getattr(host, 'address', '')), 'red')
                i += 1

        # Print the first docstring (look to the parents)
        for m in self.node.__class__.__mro__:
            if m.__module__ != 'deployer.node' and m != object and m.__doc__:
                yield termcolor.colored('  Docstring:\n', 'cyan') + \
                      termcolor.colored(m.__doc__ or '<None>', 'red')
                break

        # Actions
        yield termcolor.colored('  Actions:', 'cyan')

        def item_iterator():
            for a in Inspector(self.node).get_actions():
                yield termcolor.colored(a.name, 'red'), len(a.name)

        for line in console.in_columns(item_iterator(), margin_left=13):
            yield line

        # Nodes
        yield termcolor.colored('  Sub nodes:', 'cyan')

            # Group by node group
        grouper = lambda c:Inspector(c).get_group()
        for group, nodes in groupby(sorted(Inspector(self.node).get_childnodes(), key=grouper), grouper):
            yield termcolor.colored('         "%s"' % group.name, 'yellow')

            # Create iterator for all the items in this group
            def item_iterator():
                for n in nodes:
                    name = Inspector(n).get_name()

                    if n.parent == self.node:
                        text = termcolor.colored(name, type_of_node(n).color)
                        length = len(name)
                    else:
                        full_name = Inspector(n).get_full_name()
                        text = termcolor.colored('%s -> %s' % (name, full_name), type_of_node(n).color)
                        length = len('%s -> %s' % (name, full_name))
                    yield text, length

            # Show in columns
            for line in console.in_columns(item_iterator(), margin_left=13):
                yield line

    console.lesspipe(inspect())


@create_navigable_handler
def Cd(self):
    self.shell.state.cd(self.node)


@create_navigable_handler
def Ls(self):
    """
    List subnodes and actions in the current node.
    """
    w = self.shell.stdout.write
    console = Console(self.shell.pty)

    def run():
        # Print nodes
        if Inspector(self.node).get_childnodes():
            yield termcolor.colored(' ** Nodes **', 'cyan')
            def column_iterator():
                for c in Inspector(self.node).get_childnodes():
                    name = Inspector(c).get_name()
                    yield termcolor.colored(name, type_of_node(c).color), len(name)
            for line in console.in_columns(column_iterator()):
                yield line

        # Print actions
        if Inspector(self.node).get_actions():
            yield termcolor.colored(' ** Actions **', 'cyan')
            def column_iterator():
                for a in Inspector(self.node).get_actions():
                    yield termcolor.colored(a.name, type_of_action(a).color), len(a.name)
            for line in console.in_columns(column_iterator()):
                yield line

    console.lesspipe(run())

@create_navigable_handler
def SourceCode(self):
    """
    Print the source code of a node.
    """
    options = []

    for m in self.node.__class__.__mro__:
        if m.__module__ != 'deployer.node' and m != object:
            options.append( ('%s.%s' % (
                  termcolor.colored(m.__module__, 'red'),
                  termcolor.colored(m.__name__, 'yellow')), m) )

    if len(options) > 1:
        try:
            node_class = Console(self.shell.pty).choice('Choose node definition', options)
        except NoInput:
            return
    else:
        node_class = options[0][1]

    def run():
        try:
            # Retrieve source
            source = inspect.getsource(node_class)

            # Highlight code
            source = highlight(source, PythonLexer(), TerminalFormatter())

            for l in source.split('\n'):
                yield l.rstrip('\n')
        except IOError:
            yield 'Could not retrieve source code.'

    Console(self.shell.pty).lesspipe(run())

class Exit(ShellHandler):
    """
    Quit the deployment shell.
    """
    is_leaf = True
    handler_type = BuiltinType()

    def __call__(self):
        self.shell.exit()


class Return(ShellHandler):
    """
    Return from a subshell (which was spawned by a previous node.)
    """
    is_leaf = True
    handler_type = BuiltinType()

    def __call__(self):
        self.shell.state = self.shell.state.return_state


class Clear(ShellHandler):
    """
    Clear window.
    """
    is_leaf = True
    handler_type = BuiltinType()

    def __call__(self):
        sys.stdout.write('\033[2J\033[0;0H')
        sys.stdout.flush()


class Node(Handler):
    """
    Node node.
    """
    def __init__(self, node, shell, sandbox):
        self.node = node
        self.sandbox = sandbox
        self.shell = shell

    @property
    def is_leaf(self):
        return Inspector(self.node).is_callable()

    @property
    def handler_type(self):
        if not self.node.parent:
            # For the root node, return the built-in type
            return BuiltinType()
        else:
            return type_of_node(self.node)

    def complete_subhandlers(self, part):
        include_private = part.startswith('_')

        if self.node.parent and '..'.startswith(part):
            yield '..', Node(self.node.parent, self.shell, self.sandbox)

        if '/'.startswith(part):
            root = find_root_node(self.node)
            yield '/', Node(root, self.shell, self.sandbox)

        for action in Inspector(self.node).get_actions(include_private=include_private):
            if action.name.startswith(part):
                yield action.name, Action(self.node, action.name, self.shell, self.sandbox)

        for n in Inspector(self.node).get_childnodes(include_private=include_private):
            name = Inspector(n).get_name()
            if name.startswith(part):
                yield name, Node(n, self.shell, self.sandbox)

        for i, n in Inspector(self.node).iter_isolations(IsolationIdentifierType.HOSTS_SLUG):
            # Prefix all isolations with colons.
            name = ':%s' % ':'.join(i)
            if name.startswith(part):
                yield name, Node(n, self.shell, self.sandbox)

        if self.is_leaf and '&'.startswith(part):
            yield '&', Action(self.node, '__call__', self.shell, self.sandbox, fork=True)

    def get_subhandler(self, name):
        if name == '..' and self.node.parent:
            return Node(self.node.parent, self.shell, self.sandbox)

        elif name == '/':
            return Node(find_root_node(self.node), self.shell, self.sandbox)

        elif Inspector(self.node).has_childnode(name):
            child = Inspector(self.node).get_childnode(name)
            return Node(child, self.shell, self.sandbox)

        elif Inspector(self.node).has_action(name):
            return Action(self.node, name, self.shell, self.sandbox)

        elif name.startswith(':'):
            # Prefix all isolations with colons.
            ids = tuple(name[1:].split(':'))
            try:
                return Node(Inspector(self.node).get_isolation(ids, IsolationIdentifierType.HOSTS_SLUG),
                                    self.shell, self.sandbox)
            except AttributeError:
                pass

        elif name == '&' and self.is_leaf:
            return Action(self.node, '__call__', self.shell, self.sandbox, fork=True)

    def __call__(self):
        if self.is_leaf:
            return Action(self.node, '__call__', self.shell, self.sandbox).__call__()


class Sandbox(Node):
    handler_type = BuiltinType()

    def __init__(self, node, shell):
        Node.__init__(self, node, shell, True)


class Action(Handler):
    """
    Node action node.
    """
    is_leaf = True

    def __init__(self, node, action_name, shell, sandbox, *args, **kwargs):
        self.node = node
        self.action_name = action_name
        self.shell = shell
        self.sandbox = sandbox
        self.args = args
        self.fork = kwargs.get('fork', False)

    @property
    def handler_type(self):
        if self.fork:
            return BuiltinType()
        else:
            return type_of_node(self.node)

    def __call__(self):
        if self.fork:
            def action(pty):
                self._run_action(pty)

            self.shell.pty.run_in_auxiliary_ptys(action)
        else:
            self._run_action(self.shell.pty)

    def _run_action(self, pty):
        # Execute
        logger_interface = self.shell.logger_interface

        # Command
        command = '%s.%s()' % (Inspector(self.node).get_full_name(), self.action_name)

        try:
            env = Env(self.node, pty, logger_interface, is_sandbox=self.sandbox)
            result = getattr(env, self.action_name)(*self.args)
            supress_result = Inspector(self.node).supress_result_for_action(self.action_name)

            # When the result is a subnode, start a subshell.
            def handle_result(result):
                if isinstance(result, deployer.node.Env):
                    print ''
                    print 'Starting subshell ...'
                    self.shell.state = ShellState(result._node, return_state=self.shell.state)

                # Otherwise, print result
                elif result is not None and not supress_result:
                    print result

            if isinstance(result, list):
                for r in result:
                    handle_result(r)
            else:
                handle_result(result)

        except ActionException, e:
            # Already sent to logger_interface in the Action itself.
            pass

        except Exception, e:
            logger_interface.log_exception(e)

    def complete_subhandlers(self, part):
        # Autocompletion for the & parameter
        if not self.fork and '&'.startswith(part):
            yield '&', Action(self.node, self.action_name, self.shell, self.sandbox, *self.args, fork=True)

    def get_subhandler(self, part):
        # Get subnodes of this Action, this matches to actions with parameters.
        if self.fork:
            # Cannot write anything behind the & operator
            return None
        elif part == '&':
            return Action(self.node, self.action_name, self.shell, self.sandbox, *self.args, fork=True)
        else:
            return Action(self.node, self.action_name, self.shell, self.sandbox, *(self.args + (part,)))


class RootHandler(ShellHandler):
    subhandlers = {
            'cd': Cd,
            'clear': Clear,
            'exit': Exit,
            'find': Find,
            'ls': Ls,
            '--connect': Connect,
            '--inspect': Inspect,
            '--version': Version,
            '--source-code': SourceCode,
    }

    @property
    def current_node(self):
        return Node(self.shell.state._node, self.shell, sandbox=False)

    @property
    def sandboxed_current_node(self):
        return Sandbox(self.shell.state._node, self.shell)

    def complete_subhandlers(self, part):
        """
        Return (name, Handler) subhandler pairs.
        """
        # Default built-ins
        for name, h in self.subhandlers.items():
            if name.startswith(part):
                yield name, h(self.shell)

        # Return when the shell supports it
        if self.shell.state.can_return and 'return'.startswith(part):
            yield 'return', Return(self.shell)

        # Extensions
        for name, h in self.shell.extensions.items():
            if name.startswith(part):
                yield name, h(self.shell)

        # Sandbox
        if 'sandbox'.startswith(part):
            yield 'sandbox', self.sandboxed_current_node

        # Nodes autocomplete for 'Do' -> 'do' is optional.
        dot = self.current_node
        if '.'.startswith(part):
            yield '.', dot

        for name, h in dot.complete_subhandlers(part):
            yield name, h

    def get_subhandler(self, name):
        # Current node
        if name == '.':
            return self.current_node

        # Default built-ins
        if name in self.subhandlers:
            return self.subhandlers[name](self.shell)

        if self.shell.state.can_return and name == 'return':
            return Return(self.shell)

        if name == 'sandbox':
            return self.sandboxed_current_node

        # Extensions
        if name in self.shell.extensions:
            return self.shell.extensions[name](self.shell)

        # Nodes autocomplete for 'Do' -> 'do' is optional.
        dot = self.current_node
        return dot.get_subhandler(name)


class ShellState(object):
    """
    When we are moving to a certain position in the node tree.
    """
    def __init__(self, subnode, return_state=None):
        self._return_state = return_state
        self._node = subnode
        self._prev_node = None

    def clone(self):
        s = ShellState(self._node, self._return_state)
        s._prev_node = self._prev_node
        return s

    def __repr__(self):
        return 'ShellState(node=%r)' % self._node

    @property
    def prompt(self):
        # Returns a list of (text,color) tuples for the prompt.
        result = []
        for node in Inspector(self._node).get_path(path_type=PathType.NODE_ONLY):
            if result:
                result.append( ('.', None) )

            name = Inspector(node).get_name()
            ii = Inspector(node).get_isolation_identifier()
            color = Inspector(node).get_group().color

            result.append( (name, color) )
            if ii:
                result.append( ('[%s]' % ii, color) )
        return result

    def cd(self, target_node):
        self._prev_node = self._node
        self._node = target_node

    @property
    def can_return(self):
        return bool(self._return_state)

    @property
    def return_state(self):
        return self._return_state

    @property
    def can_cdback(self):
        return bool(self._prev_node)

    @property
    def previous_node(self):
         return self._prev_node


class Shell(CLInterface):
    """
    Deployment shell.
    """
    def __init__(self, root_node, pty, logger_interface, clone_shell=None):
        self.root_node = root_node
        self.pty = pty
        self.logger_interface = logger_interface

        if clone_shell:
            self.state = clone_shell.state.clone()
        else:
            self._reset_navigation()

        # CLI interface
        self.root_handler = RootHandler(self)
        CLInterface.__init__(self, self.pty, self.root_handler)

    def cd(self, cd_path):
        for p in cd_path:
            try:
                self.state.cd(Inspector(self.state._node).get_childnode(p))
            except AttributeError:
                print 'Unknown path given.'
                return

    def run_action(self, action_name, *a, **kw):
        """
        Run a deployment command at the current shell state.
        """
        self.state._node
        env = Env(self.state._node, self.pty, self.logger_interface, is_sandbox=False)
        return getattr(env, action_name)(*a, **kw)

    @property
    def extensions(self):
        # Dictionary with extensions to the root handler
        return { }

    def _reset_navigation(self):
        self.state = ShellState(self.root_node)

    def exit(self):
        """
        Exit cmd loop.
        """
        if self.state.can_return:
            self.state = self.state.return_state
            self.ctrl_c()
        else:
            super(Shell, self).exit()

    @property
    def prompt(self):
        """
        Return a list of [ (text, color) ] tuples representing the prompt.
        """
        return self.state.prompt + [ (' > ', 'cyan') ]
