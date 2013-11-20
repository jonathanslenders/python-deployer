from deployer.cli import CLInterface, Handler, HandlerType
from deployer.console import Console
from deployer.console import NoInput
from deployer.exceptions import ActionException
from deployer.inspection import Inspector, PathType
from deployer.node import Env, IsolationIdentifierType

from inspect import getfile
from itertools import groupby

from pygments import highlight
from pygments.formatters import TerminalFormatter
from pygments.lexers import PythonLexer

import deployer
import inspect
import socket
import sys
import termcolor


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


class ShellHandler(Handler):
    def __init__(self, shell):
        self.shell = shell


class AUTOCOMPLETE_TYPE:
    NODE = 'NODE'
    ACTION = 'ACTION'
    ACTION_AND_ARGS = 'ACTION_AND_ARGS'

    QUERY_ATTRIBUTE = 'QUERY_ATTRIBUTE'
    PROPERTY_ATTRIBUTE = 'PROPERTY'
    CONSTANT_ATTRIBUTE = 'CONNSTANT' # TODO: inspection on this type.


class NodeACHandler(ShellHandler):
    """
    ShellHandler which implements node path completion.  Depending on the
    ``autocomplete_types`` attribute, it can complete on nodes, actions, or any
    other attribute value.
    """
    autocomplete_types = [AUTOCOMPLETE_TYPE.NODE]

    def __init__(self, shell, node=None, attr_name=None, args=None):
        ShellHandler.__init__(self, shell)
        self._root = node is None
        self.node = node or shell.state._node
        self.attr_name = attr_name
        self.args = args or []

    @property
    def is_leaf(self):
        return self.get_type() is not None

    def get_type(self):
        """
        Return the ``AUTOCOMPLETE_TYPE`` for this node.
        """
        insp = Inspector(self.node)
        atypes = self.autocomplete_types

        if AUTOCOMPLETE_TYPE.NODE in atypes and not self.attr_name:
            return AUTOCOMPLETE_TYPE.NODE

        if AUTOCOMPLETE_TYPE.ACTION in atypes and not self.attr_name and insp.is_callable():
            return AUTOCOMPLETE_TYPE.ACTION

        if AUTOCOMPLETE_TYPE.ACTION in atypes and insp.has_action(self.attr_name):
            return AUTOCOMPLETE_TYPE.ACTION

        if AUTOCOMPLETE_TYPE.QUERY_ATTRIBUTE in atypes and insp.has_query(self.attr_name):
            return AUTOCOMPLETE_TYPE.QUERY_ATTRIBUTE

        if AUTOCOMPLETE_TYPE.PROPERTY_ATTRIBUTE in atypes and insp.has_property(self.attr_name):
            return AUTOCOMPLETE_TYPE.PROPERTY_ATTRIBUTE

    @property
    def handler_type(self):
        if self._root:
            return BuiltinType()
        else:
            node_color = Inspector(self.node).get_group().color

            def get_postfix():
                type_ = self.get_type()
                if type_ == AUTOCOMPLETE_TYPE.ACTION:
                    return '*'

                if type_ == AUTOCOMPLETE_TYPE.QUERY_ATTRIBUTE:
                    return '?'

                if type_ == AUTOCOMPLETE_TYPE.PROPERTY_ATTRIBUTE:
                    return '@'

                return ''

            class Type(HandlerType):
                color = node_color
                postfix = get_postfix()
            return Type()

    def get_subhandler(self, name):
        parent = self.node.parent
        cls = self.__class__

        # Current node
        if name == '.':
            return self

        # Previous location
        if name == '-' and self.shell.state.can_cdback:
            return cls(self.shell, self.shell.state.previous_node)

        # Root node
        if parent and name == '/':
            root = Inspector(parent).get_root()
            return cls(self.shell, root)

        # Parent node
        if parent and name == '..':
            return cls(self.shell, parent)

        # TODO: ~ --> home.

        # Isolation
        elif name.startswith(':'):
            ids = tuple(name[1:].split(':'))
            try:
                node = Inspector(self.node).get_isolation(ids, IsolationIdentifierType.HOSTS_SLUG)
                return cls(self.shell, node)
            except AttributeError: pass

        # Childnodes
        try:
            node = Inspector(self.node).get_childnode(name)
            return cls(self.shell, node)
        except AttributeError: pass

        # Actions
        if AUTOCOMPLETE_TYPE.ACTION in self.autocomplete_types:
            try:
                action = Inspector(self.node).get_action(name)
                return cls(self.shell, self.node, name)
            except AttributeError: pass

        if AUTOCOMPLETE_TYPE.ACTION_AND_ARGS in self.autocomplete_types and self.attr_name:
            return cls(self.shell, self.node, self.attr_name, self.args + [name])

        # Queries
        if AUTOCOMPLETE_TYPE.QUERY_ATTRIBUTE in self.autocomplete_types:
            try:
                action = Inspector(self.node).get_query(name)
                return cls(self.shell, self.node, action.name)
            except AttributeError:
                pass

        # Properties
        if AUTOCOMPLETE_TYPE.PROPERTY_ATTRIBUTE in self.autocomplete_types:
            try:
                action = Inspector(self.node).get_property(name)
                return cls(self.shell, self.node, action.name)
            except AttributeError:
                pass

    def complete_subhandlers(self, part):
        parent = self.node.parent
        include_private = part.startswith('_')
        cls = self.__class__

        # No autocompletion anymore after an action has been typed.
        if self.attr_name:
            return

        # Current node
        if '.'.startswith(part):
            yield '.', self

        # Previous location
        if '-'.startswith(part) and self.shell.state.can_cdback:
            yield '-', cls(self.shell, self.shell.state.previous_node)

        # Root node
        if parent and '/'.startswith(part):
            root = Inspector(parent).get_root()
            yield '/', cls(self.shell, root)

        # Parent node
        if parent and '..'.startswith(part):
            yield ('..', cls(self.shell, parent))

        # TODO: ~ -->> Home

        # Isolation
        for i, n in Inspector(self.node).iter_isolations(IsolationIdentifierType.HOSTS_SLUG):
            if i:
                # Prefix all isolations with colons.
                name = ':%s' % ':'.join(i)
                if name.startswith(part):
                    yield name, cls(self.shell, n)

        # Childnodes:
        # Note: when an underscore has been typed, include private too.
        for c in Inspector(self.node).get_childnodes(include_private=include_private):
            name = Inspector(c).get_name()
            if name.startswith(part):
                yield name, cls(self.shell, c)

        # Actions
        if AUTOCOMPLETE_TYPE.ACTION in self.autocomplete_types:
            for action in Inspector(self.node).get_actions(include_private=include_private):
                if action.name.startswith(part):
                    yield action.name, cls(self.shell, self.node, action.name)

        # Queries
        if AUTOCOMPLETE_TYPE.QUERY_ATTRIBUTE in self.autocomplete_types:
            for action in Inspector(self.node).get_queries(include_private=include_private):
                if action.name.startswith(part):
                    yield action.name, cls(self.shell, self.node, action.name)

        # Properties
        if AUTOCOMPLETE_TYPE.PROPERTY_ATTRIBUTE in self.autocomplete_types:
            for action in Inspector(self.node).get_properties(include_private=include_private):
                if action.name.startswith(part):
                    yield action.name, cls(self.shell, self.node, action.name)


    def __call__(self):
        raise NotImplementedError


# Handlers


class Version(ShellHandler):
    is_leaf = True
    handler_type = BuiltinType()

    def __call__(self):
        print termcolor.colored('  deployer library, version: ', 'cyan'),
        print termcolor.colored(deployer.__version__, 'red')
        print termcolor.colored('  Host:                      ', 'cyan'),
        print termcolor.colored(socket.gethostname(), 'red')
        print termcolor.colored('  Root node class:           ', 'cyan'),
        print termcolor.colored(self.shell.root_node.__module__, 'red'),
        print termcolor.colored('  <%s>' % self.shell.root_node.__class__.__name__, 'red')


class Connect(NodeACHandler):
    """
    Open interactive SSH connection with this host.
    """
    def __call__(self):
        from deployer.contrib.nodes import connect

        class Connect(connect.Connect):
            class Hosts:
                host = self.node.hosts.get_hosts()

        env = Env(Connect(), self.shell.pty, self.shell.logger_interface)

        # Run as any other action. (Nice exception handling, e.g. in case of NoInput on host selection.)
        try:
            env.with_host()
        except ActionException as e:
            pass
        except Exception as e:
            self.shell.logger_interface.log_exception(e)


class Run(NodeACHandler):
    """
    Run a shell command on all hosts in the current node.
    """
    use_sudo = False

    def get_command(self):
        try:
            text = '[SUDO] Enter command' if self.use_sudo else 'Enter command'
            return Console(self.shell.pty).input(text)
        except NoInput:
            return

    def __call__(self):
        from deployer.node import Node

        # Print info
        host_count = len(self.node.hosts)

        if host_count == 0:
            print 'No hosts found at this node. Nothing to execute.'
            return

        print 'Command will be executed on %i hosts:' % host_count
        for h in self.node.hosts:
            print '   - %s (%s)' % (h.slug, h.address)

        command = self.get_command()
        if not command:
            return

        # Run
        use_sudo = self.use_sudo

        class RunNode(Node):
            class Hosts:
                host = self.node.hosts.get_hosts()

            def run(self):
                if use_sudo:
                    self.hosts.sudo(command)
                else:
                    self.hosts.run(command)

        env = Env(RunNode(), self.shell.pty, self.shell.logger_interface)

        # Run as any other action. (Nice exception handling, e.g. in case of
        # NoInput on host selection.)
        try:
            env.run()
        except ActionException as e:
            pass
        except Exception as e:
            self.shell.logger_interface.log_exception(e)


class RunWithSudo(Run):
    use_sudo = True


class Find(NodeACHandler):
    def __call__(self):
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


class Inspect(NodeACHandler):
    """
    Inspection of the current node. Show host mappings and other information.
    """
    autocomplete_types = [
            AUTOCOMPLETE_TYPE.NODE,
            AUTOCOMPLETE_TYPE.ACTION,
            AUTOCOMPLETE_TYPE.QUERY_ATTRIBUTE,
            AUTOCOMPLETE_TYPE.PROPERTY_ATTRIBUTE ]

    def __call__(self):
        type_ = self.get_type()

        if type_ == AUTOCOMPLETE_TYPE.NODE:
            self._inspect_node()

        if type_ == AUTOCOMPLETE_TYPE.ACTION:
            self._inspect_action()

        if type_ == AUTOCOMPLETE_TYPE.QUERY_ATTRIBUTE:
            self._inspect_query_attribute()

        if type_ == AUTOCOMPLETE_TYPE.PROPERTY_ATTRIBUTE:
            self._inspect_property_attribute()

    def _inspect_node(self):
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

    def _inspect_action(self):
        console = Console(self.shell.pty)
        action = Inspector(self.node).get_action(self.attr_name)

        def run():
            yield termcolor.colored('  Action name:   ', 'cyan') + \
                  termcolor.colored(self.attr_name, 'yellow')
            yield termcolor.colored('  __repr__:      ', 'cyan') + \
                  termcolor.colored(repr(action._func), 'yellow')
            yield termcolor.colored('  Node:          ', 'cyan') + \
                  termcolor.colored(repr(self.node), 'yellow')
        console.lesspipe(run())

    def _get_env(self):
        """
        Created a sandboxed environment for evaluation of attributes.
        (attributes shouldn't have side effects on servers, so sandboxing is fine.)
        Returns an ``Env`` object.
        """
        env = Env(self.node, self.shell.pty, self.shell.logger_interface, is_sandbox=True)
        return Console(self.shell.pty).select_node_isolation(env)

    def _inspect_query_attribute(self):
        console = Console(self.shell.pty)
        query = Inspector(self.node).get_query(self.attr_name).query

        def run():
            yield termcolor.colored('  Node:       ', 'cyan') + \
                  termcolor.colored(Inspector(self.node).get_full_name(), 'yellow')
            yield termcolor.colored('  Filename:   ', 'cyan') + \
                  termcolor.colored(query._filename, 'yellow')
            yield termcolor.colored('  Line:       ', 'cyan') + \
                  termcolor.colored(query._line, 'yellow')
            yield termcolor.colored('  Expression: ', 'cyan') + \
                  termcolor.colored(repr(query.query), 'yellow')
            yield ''

            # Execute query in sandboxed environment.
            yield 'Trace query:'
            try:
                insp = Inspector(self._get_env())
                result = insp.trace_query(self.attr_name)
            except Exception as e:
                yield 'Failed to execute query: %r' % e
                return

            # Print query and all subqueries with their results.
            for subquery in result.walk_through_subqueries():
                yield termcolor.colored(repr(subquery[0]), 'cyan')
                yield '    %s' % subquery[1]

        console.lesspipe(run())

    def _inspect_property_attribute(self):
        console = Console(self.shell.pty)
        action = Inspector(self.node).get_property(self.attr_name)

        def run():
            yield termcolor.colored('  Property name:   ', 'cyan') + \
                  termcolor.colored(self.attr_name, 'yellow')
            yield termcolor.colored('  __repr__:      ', 'cyan') + \
                  termcolor.colored(repr(action._func), 'yellow')
            yield termcolor.colored('  Node:          ', 'cyan') + \
                  termcolor.colored(repr(self.node), 'yellow')

            # Value
            try:
                value = getattr(self._get_env(), self.attr_name)

                yield termcolor.colored('  Value:          ', 'cyan') + \
                      termcolor.colored(repr(value), 'yellow')
            except Exception as e:
                yield termcolor.colored('  Value:          ', 'cyan') + \
                      termcolor.colored('Failed to evaluate value...', 'yellow')
        console.lesspipe(run())


class Cd(NodeACHandler):
    def __call__(self):
        self.shell.state.cd(self.node)


class Ls(NodeACHandler):
    """
    List subnodes and actions in the current node.
    """
    def __call__(self):
        w = self.shell.stdout.write
        console = Console(self.shell.pty)

        def run():
            # Print nodes
            if Inspector(self.node).get_childnodes():
                yield 'Child nodes:'

                def column_iterator():
                    for c in Inspector(self.node).get_childnodes():
                        name = Inspector(c).get_name()
                        yield termcolor.colored(name, type_of_node(c).color), len(name)
                for line in console.in_columns(column_iterator()):
                    yield line

            # Print actions
            if Inspector(self.node).get_actions():
                yield 'Actions:'

                def column_iterator():
                    for a in Inspector(self.node).get_actions():
                        yield termcolor.colored(a.name, type_of_action(a).color), len(a.name)
                for line in console.in_columns(column_iterator()):
                    yield line

        console.lesspipe(run())

class Pwd(NodeACHandler):
    """
    Print current node path.
    ``pwd``, like "Print working Directory" in the Bash shell.
    """
    def __call__(self):
        result = [ ]

        for node, name in Inspector(self.node).get_path(PathType.NODE_AND_NAME):
            color = Inspector(node).get_group().color
            result.append(termcolor.colored(name, color))

        sys.stdout.write(termcolor.colored('/', 'cyan'))
        sys.stdout.write(termcolor.colored('.', 'cyan').join(result) + '\n')
        sys.stdout.flush()


class SourceCode(NodeACHandler):
    """
    Print the source code of a node.
    """
    def __call__(self):
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


class Scp(NodeACHandler):
    """
    Open a secure copy shell at this node.
    """
    def __call__(self):
        # Choose host.
        hosts = self.node.hosts.get_hosts()
        if len(hosts) == 0:
            print 'No hosts found'
            return
        elif len(hosts) == 1:
            host = hosts.copy().pop()
        else:
            # Choose a host.
            options = [ (h.slug, h) for h in hosts ]
            try:
                host = Console(self.shell.pty).choice('Choose a host', options, allow_random=True)
            except NoInput:
                return

        # Start scp shell
        from deployer.scp_shell import Shell
        Shell(self.shell.pty, host, self.shell.logger_interface).cmdloop()


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


class Node(NodeACHandler):
    """
    Node node.
    """
    sandbox = False
    autocomplete_types = [
            AUTOCOMPLETE_TYPE.ACTION,
            AUTOCOMPLETE_TYPE.ACTION_AND_ARGS,
            ]

    def __call__(self):
        # Execute
        logger_interface = self.shell.logger_interface

        try:
            # Create env
            env = Env(self.node, self.shell.pty, logger_interface, is_sandbox=self.sandbox)

            # Call action
            if self.attr_name is not None:
                result = getattr(env, self.attr_name)(*self.args)
                suppress_result = Inspector(self.node).suppress_result_for_action(self.attr_name)
            else:
                result = env(*self.args)
                suppress_result = False

            # When the result is a subnode, start a subshell.
            def handle_result(result):
                if isinstance(result, deployer.node.Env):
                    print ''
                    print 'Starting subshell ...'
                    self.shell.state = ShellState(result._node, return_state=self.shell.state)

                # Otherwise, print result
                elif result is not None and not suppress_result:
                    print result

            if isinstance(result, list):
                for r in result:
                    handle_result(r)
            else:
                handle_result(result)

        except ActionException as e:
            # Already sent to logger_interface in the Action itself.
            pass

        except Exception as e:
            logger_interface.log_exception(e)


class Sandbox(Node):
    sandbox = True


class RootHandler(ShellHandler):
    subhandlers = {
            'cd': Cd,
            'clear': Clear,
            'exit': Exit,
            'find': Find,
            'ls': Ls,
            'sandbox': Sandbox,
            'pwd': Pwd,
            '--connect': Connect,
            '--inspect': Inspect,
            '--run': Run,
            '--run-with-sudo': RunWithSudo,
            '--version': Version,
            '--source-code': SourceCode,
            '--scp': Scp,
    }

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

        # Nodes.
        for name, h in Node(self.shell).complete_subhandlers(part):
            yield name, h

    def get_subhandler(self, name):
        # Current node
        if name == '.':
            return Node(self.shell)

        # Default built-ins
        if name in self.subhandlers:
            return self.subhandlers[name](self.shell)

        if self.shell.state.can_return and name == 'return':
            return Return(self.shell)

        # Extensions
        if name in self.shell.extensions:
            return self.shell.extensions[name](self.shell)

        # Nodes.
        return Node(self.shell).get_subhandler(name)


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

    @property
    def node(self):
        return self._node


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

    def open_scp_shell(self):
        self.root_handler.get_subhandler('--scp')()

    def run_action(self, action_name, *a, **kw):
        """
        Run a deployment command at the current shell state.
        """
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
