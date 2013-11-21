from deployer.console import Console
from deployer.exceptions import ExecCommandFailed, ActionException
from deployer.groups import Group
from deployer.host import Host
from deployer.host_container import HostsContainer, HostContainer
from deployer.loggers import DummyLoggerInterface
from deployer.node.role_mapping import RoleMapping, ALL_HOSTS, DefaultRoleMapping
from deployer.pseudo_terminal import DummyPty
from deployer.query import Query
from deployer.utils import isclass

from inspect import isfunction

import logging
import traceback


__all__ = (
    'Action',
    'Env',
    'EnvAction',
    'IsolationIdentifierType',
    'Node',
    'NodeBase',
    'SimpleNode',
    'SimpleNodeBase',
    'iter_isolations',
    'required_property',
)


class required_property(property):
    """
    Placeholder for properties which are required
    when a service is inherit.
    """
    def __init__(self, description=''):
        self.description = description
        self.name = ''
        self.owner = ''

        def fget(obj):
            raise NotImplementedError('Required property %s of %s is not defined: %s' %
                            (self.name, self.owner, self.description))

        property.__init__(self, fget)


class ChildNodeDescriptor(object):
    """
    Every nested Node class definition in a Node will be wrapped by this descriptor. For instance:

    >> class ParentNode(Node):
    >>     class ChildNode(Node):
    >>         pass
    """
    def __init__(self, attr_name, node_class):
        self.attr_name = attr_name
        self._node_class = node_class

    def __get__(self, parent_instance, owner):
        """
        When the child node is retrieved from an instance of the parent node, an instance of the child node
        will be returned (and the hosts from the parent are mapped to the child.)
        """
        if parent_instance:
            new_name = '%s.%s' % (owner.__name__, self.attr_name)

            # When The parent is isolated, return an isolated childnode, except if we have an Array.
            isolated = (parent_instance._node_is_isolated and self._node_class._node_type != NodeTypes.SIMPLE_ARRAY)

            # We inherit the class in order to override the name and isolated
            # attributes. However, the creation counter should stay the same,
            # because it's used to track the order of childnodes in the parent.
            class_ = type(new_name, (self._node_class, ), {
                            '_node_is_isolated': isolated,
                            '_node_name': self.attr_name
                            })
            class_._node_creation_counter = self._node_class._node_creation_counter

            return class_(parent=parent_instance)
        else:
            return self._node_class


class QueryDescriptor(object):
    def __init__(self, node_name, attr_name, query):
        self.node_name = node_name
        self.attr_name = attr_name
        self.query = query

    def __get__(self, instance, owner):
        if instance:
            return Action.from_query(self.attr_name, instance, self.query)
        else:
            return self.query


class ActionDescriptor(object):
    """
    Every instancemethod in a Service will be wrapped by this descriptor.
    """
    def __init__(self, attr_name, func):
        self.attr_name = attr_name
        self._func = func

    def __get__(self, node_instance, owner):
        if node_instance:
            return Action(self.attr_name, node_instance, self._func)
        else:
            # Unbound action access. We need this for calling the method of a
            # super class. e.g. Config.action(env, *a...)
            return Action(self.attr_name, None, self._func)


class PropertyDescriptor(object):
    def __init__(self, attr_name, attribute):
        self.attr_name = attr_name
        self.attribute = attribute

    def __get__(self, instance, owner):
        if instance:
            return Action.from_property(self.attr_name, instance, self.attribute.fget)
        else:
            return self.attribute


class Env(object):
    """
    Wraps a :class:`deployer.node.Node` into an executable context.

    ::

        n = Node()
        e = Env(n)
        e.do_action()

    Instead of ``self``, the first parameter of a ``Node``-action will be this
    ``Env`` instance. It acts like a proxy to the ``Node``, but in the meantime
    it takes care of logging, sandboxing, the terminal and context.

    .. note:: Node actions can never be executed directly on the node instance,
              without wrapping it in an Env object first. But if you use the
              :ref:`interactive shell <interactive-shell>`, the shell will do this
              for you.

    :param node: The node that this ``Env`` should wrap.
    :type node: :class:`deployer.node.Node`
    :param pty: The terminal object that wraps the input and output streams.
    :type pty: :class:`deployer.pseudo_terminal.Pty`
    :param logger: (optional) The logger interface.
    :type logger: :class:`deployer.logger.LoggerInterface`
    :param is_sandbox: Run all commands in here in sandbox mode.
    :type is_sandbox: bool
    """
    def __init__(self, node, pty=None, logger=None, is_sandbox=False):
        assert isinstance(node, Node)

        self._node = node
        self._pty = pty or DummyPty()
        self._logger = logger or DummyLoggerInterface()
        self._is_sandbox = is_sandbox

        # When the node is callable (when it has a default action),
        # make sure that this env becomes collable as well.
        if callable(self._node):
            # Per instance overriding
            def call(self, *a, **kw):
                return self.__getattr__('__call__')(*a, **kw)

            self.__class__ = type(self.__class__.__name__, (self.__class__,), { '__call__': call })

        # Create a new HostsContainer object which is identical to the one of
        # the Node object, but add pty/logger/sandbox settings. (So, this
        # doesn't create new Host instances, only a new container.)
        # (do this in this constructor. Each call to Env.hosts should return
        # the same host container instance.)
        self._hosts = HostsContainer(self._node.hosts.get_hosts_as_dict(), pty=self._pty,
                                logger=self._logger, is_sandbox=is_sandbox)

        # Lock Env
        self._lock_env = True

    def __repr__(self):
        return 'Env(%s)' % get_node_path(self._node)

    def __wrap_action(self, action, auto_evaluate=True):
        """
        Wrap the action in an EnvAction object when it's called from the Env.
        This will make sure that __call__ will run it in this Env environment.

        :param auto_evaluate: Call properties and queries immediately upon retrieval.
                              This is the default behaviour.
        :type auto_evaluate: bool
        """
        assert isinstance(action, Action)
        env_action = EnvAction(self, action)

        if (action.is_property or action.is_query) and auto_evaluate:
            # Properties are automatically called upon retrieval
            return env_action()
        else:
            return env_action

    def initialize_node(self, node_class):
        """
        Dynamically initialize a node from within another node.
        This will make sure that the node class is initialized with the
        correct logger, sandbox and pty settings. e.g:

        :param node_class: A ``Node`` subclass.

        ::

            class SomeNode(Node):
                def action(self):
                    pass

            class RootNode(Node):
                def action(self):
                    # Wrap SomeNode into an Env object
                    node = self.initialize_node(SomeNode)

                    # Use the node.
                    node.action2()
        """
        return self.__wrap_node(node_class())

    def __wrap_node(self, node):
        assert isinstance(node, Node)
        return Env(node, self._pty, self._logger, self._is_sandbox)

    @property
    def hosts(self):
        """
        :class:`deployer.host_container.HostsContainer` instance. This is the
        proxy to the actual hosts.
        """
        return self._hosts

    @property
    def console(self):
        """
        Interface for user input. Returns a :class:`deployer.console.Console`
        instance.
        """
        if not self._pty:
            raise AttributeError('Console is not available in Env when no pty was given.')
        return Console(self._pty)

    def __getattr__(self, name):
        """
        Retrieve attributes from the Node class, but in case of actions and
        childnodes, wrap it in this environment.
        """
        attr = getattr(self._node, name)

        if isinstance(attr, Action):
            return self.__wrap_action(attr)

        elif isinstance(attr, Node):
            return self.__wrap_node(attr)

        else:
            return attr

    def __setattr__(self, name, value):
        # Only allow setting of attributes when the _lock_env flag has not yet been set.
        try:
            locked = object.__getattribute__(self, '_lock_env')
        except AttributeError, e:
            locked = False

        if locked:
            raise AttributeError('Not allowed to change attributes of the node environment. (%s=%r)' % (name, value))
        else:
            super(Env, self).__setattr__(name, value)

    def __iter__(self):
        for node in self._node:
            yield self.__wrap_node(node)

    def __getitem__(self, item):
        return self.__wrap_node(self._node[item])


class NodeTypes:
    NORMAL = 'NORMAL_NODE'
    SIMPLE = 'SIMPLE_NODE'
    SIMPLE_ARRAY = 'SIMPLE_NODE.ARRAY'
    SIMPLE_ONE = 'SIMPLE_NODE.ONE'

class MappingOptions:
    REQUIRED = 'MAPPING_REQUIRED'
    OPTIONAL = 'MAPPING_OPTIONAL'
    NOT_ALLOWED = 'MAPPING_NOT_ALLOWED'


class NodeNestingRules:
    RULES = {
            # Parent - Child
            (NodeTypes.NORMAL, NodeTypes.NORMAL): MappingOptions.OPTIONAL,
            (NodeTypes.NORMAL, NodeTypes.SIMPLE_ARRAY): MappingOptions.REQUIRED,
            (NodeTypes.NORMAL, NodeTypes.SIMPLE_ONE): MappingOptions.REQUIRED,

            (NodeTypes.SIMPLE_ARRAY, NodeTypes.SIMPLE): MappingOptions.OPTIONAL,
            (NodeTypes.SIMPLE_ONE, NodeTypes.SIMPLE): MappingOptions.OPTIONAL,
            (NodeTypes.SIMPLE, NodeTypes.SIMPLE): MappingOptions.OPTIONAL,

            (NodeTypes.SIMPLE, NodeTypes.NORMAL): MappingOptions.OPTIONAL,
            (NodeTypes.SIMPLE_ARRAY, NodeTypes.NORMAL): MappingOptions.OPTIONAL,
            (NodeTypes.SIMPLE_ONE, NodeTypes.NORMAL): MappingOptions.OPTIONAL,
    }
    @classmethod
    def check(cls, parent, child):
        return (parent, child) in cls.RULES

    @classmethod
    def check_mapping(cls, parent, child, has_mapping):
        mapping_option = cls.RULES[(parent, child)]

        if has_mapping:
            return mapping_option in (MappingOptions.OPTIONAL, MappingOptions.REQUIRED)
        else:
            return mapping_option in (MappingOptions.OPTIONAL, MappingOptions.NOT_ALLOWED)


def _internal(func):
    """ Mark this function as internal. """
    func.internal = True
    return func


class NodeBase(type):
    """
    Metaclass for Node. This takes mostly care of wrapping Node members
    into the correct descriptor, but it does some metaclass magic.
    """
    # Keep track of the order in which nodes are created, so that we can
    # retain the order of nested sub nodes. This global variable is
    # increased after every definition of a Node class.
    creation_counter = 0

    @classmethod
    def _preprocess_attributes(cls, attrs, base):
        """
        Do double-underscore preprocessing of attributes.
        e.g.
        `server__ssl_is_enabled = True` will override the `ssl_is_enabled`
        value of the server object in attrs.
        """
        new_attrs = { }
        override = { } # { attr_to_override: { k->v } }

        # Separate real attributes from "nested overrides".
        for k, v in attrs.items():
            if '__' in k and not k.startswith('__'): # Allow name mangling.
                # Split at __ (only split at the first __, type(...) below
                # does it recursively.)
                attr_to_override, key = k.split('__', 1)

                if attr_to_override in override:
                    override[attr_to_override][key] = v
                else:
                    override[attr_to_override] = { key : v }
            else:
                new_attrs[k] = v

        # Now apply overrides.
        for attr, overrides in override.items():
            first_override = overrides.keys()[0]

            if attr in new_attrs:
                raise Exception("Don't override %s__%s property in the same scope." %
                                (attr, first_override))
            elif hasattr(base, attr):
                original_node = getattr(base, attr)

                if not issubclass(original_node, Node):
                    raise Exception('Node override %s__%s is not applied on a Node class.' %
                                    (attr, first_override))
                else:
                    new_attrs[attr] = type(attr, (original_node,), overrides)
            else:
                raise Exception("Couldn't find %s__%s to override." % (attr, first_override))

        return new_attrs

    def __new__(cls, name, bases, attrs):
        # No multiple inheritance allowed.
        if len(bases) > 1:
            # Not sure whether this is a good idea or not, it might be not that bad...
            raise Exception('No multiple inheritance allowed for Nodes')

        # Preprocess __ in attributes
        attrs = cls._preprocess_attributes(attrs, bases[0])

        # Get node type.
        if '_node_type' in attrs:
            node_type = attrs['_node_type']
        else:
            node_type = bases[0]._node_type

        # Do not allow __init__ to be overriden
        if '__init__' in attrs and not getattr(attrs['__init__'], 'internal', False):
            raise TypeError('A Node should not have its own __init__ function.')

        # Verify that nobody is overriding the 'host' property.
        if 'host' in attrs and (
                not isinstance(attrs['host'], property) or
                not getattr(attrs['host'].fget, '_internal', False)):
            raise TypeError("Please don't override the reserved name 'host' in a Node.")

        if name != 'Node': # TODO: this "!='Node'" may not be completely safe...
            # Replace actions/childnodes/properties by descriptors
            for attr_name, attr in attrs.items():
                wrapped_attribute = cls._wrap_attribute(attr_name, attr, name, node_type)
                attrs[attr_name] = wrapped_attribute

                if isfunction(attr):
                    # Create aliases
                    if hasattr(attr, 'action_alias'):
                        for a in attr.action_alias:
                            attrs[a] = cls._wrap_attribute(a, attr, name, node_type)

        # Set creation order
        attrs['_node_creation_counter'] = cls.creation_counter
        cls.creation_counter += 1

        # Create class
        return type.__new__(cls, name, bases, attrs)

    @classmethod
    def _wrap_attribute(cls, attr_name, attribute, node_name, node_type):
        """
        Wrap a Node attribute into the correct descriptor class.
        """
        # The Hosts definition (should be a Hosts class ore RoleMapping)
        if attr_name == 'Hosts':
            # Validate 'Hosts' value
            if not isinstance(attribute, RoleMapping):
                if isclass(attribute):
                    # Try to initialize a HostContainer. If that fails, something is wrong.
                    HostsContainer.from_definition(attribute)
                else:
                    raise Exception('Node.Hosts should be a class definition or a RoleMapping instance.')
            return attribute

        # Wrap functions into an ActionDescriptor
        elif isfunction(attribute) and attr_name not in ('__getitem__', '__iter__', '__new__', '__init__'):
            return ActionDescriptor(attr_name, attribute)

        # Wrap Nodes into a ChildNodeDescriptor
        elif isclass(attribute) and issubclass(attribute, Node):
            # Check the node nesting rules.
            if not NodeNestingRules.check(node_type, attribute._node_type):
                raise Exception('Invalid nesting of %s in %s (%r in %r).' % (
                            attribute._node_type, node_type, attribute, node_name))

            if not NodeNestingRules.check_mapping(node_type, attribute._node_type, bool(attribute.Hosts)):
                raise Exception('The Node-attribute %s of type %s does not have a valid role_mapping.' %
                                            (attr_name, attribute._node_type))


            return ChildNodeDescriptor(attr_name, attribute)

        # Properties should be wrapped again in an Action
        # descriptor
        elif isinstance(attribute, property):
            if isinstance(attribute, required_property):
                attribute.name = attr_name
                attribute.owner = node_name
            return PropertyDescriptor(attr_name, attribute)

        # Query objects are like properties and should also be
        # wrapped into a descriptor
        elif isinstance(attribute, Query):
            return QueryDescriptor(node_name, attr_name, attribute)

        else:
            return attribute

    def __setattr__(self, name, value):
        """
        When dynamically, a new function/property/class is assigned to a
        Node class definition, wrap it into the correct descriptor, before
        assigning it to the actual class.
        Note that `self` is a Node class here, not a Node instance.
        """
        wrapped_attribute = self._wrap_attribute(name, value, self.__name__, self._node_type)
        type.__setattr__(self, name, wrapped_attribute)

    def __instancecheck__(self, instance):
        """
        Override isinstance operator.
        We consider an Env object in instance of this class as well if
        env._node is an instance.
        """
        return type.__instancecheck__(self, instance) or (
                    isinstance(instance, Env) and isinstance(instance._node, self))


class SimpleNodeBase(NodeBase):
    @property
    def Array(self):
        """
        'Arrayify' a SimpleNode. This is an explicit step
        to be taken before nesting SimpleNode into a normal Node.
        """
        if self._node_type != NodeTypes.SIMPLE:
            raise Exception('Second .Array operation is not allowed.')

        # When this class doesn't have a Hosts, create default mapper.
        hosts = RoleMapping(host=ALL_HOSTS) if self.Hosts is None else self.Hosts

        class SimpleNodeArray(self):
            _node_type = NodeTypes.SIMPLE_ARRAY
            Hosts = hosts

        SimpleNodeArray.__name__ = '%s.Array' % self.__name__
        return SimpleNodeArray

    @property
    def JustOne(self):
        """
        When nesting SimpleNode inside a normal Node,
        say that we expect exactly one host for the mapped
        role, so don't act like an array.
        """
        if self._node_type != NodeTypes.SIMPLE:
            raise Exception('Second .JustOne operation is not allowed.')

        # When this class doesn't have a Hosts, create default mapper.
        hosts = RoleMapping(host=ALL_HOSTS) if self.Hosts is None else self.Hosts

        class SimpleNode_One(self):
            _node_type = NodeTypes.SIMPLE_ONE
            Hosts = hosts

            @_internal
            def __init__(self, parent):
                Node.__init__(self, parent)
                if len(self.hosts.filter('host')) != 1:
                    raise Exception('Invalid initialisation of SimpleNode.JustOne. %i hosts given to %r.' %
                            (len(self.hosts.filter('host')), self))


        SimpleNode_One.__name__ = '%s.JustOne' % self.__name__
        return SimpleNode_One


def get_node_path(node): # TODO: maybe replace this by using the inspection module.
    """
    Return a string which represents this node's path in the tree.
    """
    path = []
    while node:
        if node._node_isolation_identifier is not None:
            path.append('%s[%s]' % (node._node_name, node._node_isolation_identifier))
        else:
            path.append(node._node_name or node.__class__.__name__)
        node = node.parent
    return '.'.join(path[::-1])


class Node(object):
    """
    This is the base class for any deployment node.

    For the attributes, also have a look at the proxy class
    :class:`deployer.node.Env`. The ``parent`` parameter is used internally to
    pass the parent ``Node`` instance into here.
    """
    __metaclass__ = NodeBase
    __slots__ = ('hosts', 'parent')
    _node_type = NodeTypes.NORMAL
    _node_is_isolated = False
    _node_isolation_identifier = None
    _node_name = None # NodeBase will set this to the attribute name as soon as we nest this node inside another one.

    node_group = None # TODO: rename to _node_group??

    Hosts = None
    """
    Hosts can be ``None`` or a definition of the hosts that should be used for this node.
    e.g.::

        class MyNode(Node):
            class Hosts:
                role1 = [ LocalHost ]
                role2 = [ SSHHost1, SSHHost2]
    """

    def __repr__(self):
        return '<Node %s>' % get_node_path(self)

    def __new__(cls, parent=None):
        """
        When this is the root node, of type NORMAL, mark is isolated right away.
        """
        if not parent and cls._node_type == NodeTypes.NORMAL:
            new_cls = type(cls.__name__, (cls,), { '_node_is_isolated': True })
            return object.__new__(new_cls, parent)
        else:
            return object.__new__(cls, parent)

    @_internal
    def __init__(self, parent=None):
        self.parent = parent
        if self._node_type in (NodeTypes.SIMPLE_ARRAY, NodeTypes.SIMPLE_ONE) and not parent:
            raise Exception('Cannot initialize a node of type %s without a parent' % self._node_type)

        # Create host container (from hosts definition, or mapping from parent hosts.)
        Hosts = self.Hosts or DefaultRoleMapping()

        if isinstance(Hosts, RoleMapping):
            self.hosts = Hosts.apply(parent) if parent else HostsContainer({ })
        else:
            self.hosts = HostsContainer.from_definition(Hosts)

        # TODO: when this is a SimpleNode and a parent was given, do we have to make sure that the
        #       the 'host' is the same, when a mapping was given? I don't think it's necessary.

    def __getitem__(self, index):
        """
        When this is a not-yet-isolated SimpleNode,
        __getitem__ retrieves the instance for this host.

        This returns a specific isolation. In case of multiple dimensions
        (multiple Node-SimpleNode.Array transitions, a tuple should be provided.)
        """
        if self._node_is_isolated:
            # TypeError, would also be a good, idea, but we choose to be compatible
            # with the error class for when an item is not found.
            raise KeyError('__getitem__ on isolated node is not allowed.')

        if isinstance(index, HostContainer):
            index = (index._host.__class__, )

        if not isinstance(index, tuple):
            index = (index, )

        for identifier_type in [
                        IsolationIdentifierType.INT_TUPLES,
                        IsolationIdentifierType.HOST_TUPLES,
                        IsolationIdentifierType.HOSTS_SLUG ]:

            for key, node in iter_isolations(self, identifier_type):
                if key == index:
                    return node
        raise KeyError

    def __iter__(self):
        for key, node in iter_isolations(self):
            yield node


class IsolationIdentifierType:
    """
    Manners of identifing a node in an array of nodes.
    """
    INT_TUPLES = 'INT_TUPLES'
    """ Use a tuple of integers """

    HOST_TUPLES = 'HOST_TUPLES'
    """ Use a tuple of :class:`Host` classes """

    HOSTS_SLUG = 'HOSTS_SLUG'
    """ Use a tuple of :class:`Host` slugs """


def iter_isolations(node, identifier_type=IsolationIdentifierType.INT_TUPLES):
    """
    Yield (index, Node) for each isolation of this node.
    """
    assert isinstance(node, Node) and not isinstance(node, Env)

    if node._node_is_isolated:
        yield (), node
        return

    def get_simple_node_cell(parent, host, identifier):
        """
        For a SimpleNode (or array cell), create a SimpleNode instance which
        matches a single cell, that is one Host for the 'host'-role.
        """
        assert isinstance(host, Host)
        hosts2 = node.hosts.get_hosts_as_dict()
        hosts2['host'] = host.__class__

        class SimpleNodeItem(node.__class__):
            _node_is_isolated = True
            _node_isolation_identifier = identifier
            Hosts = type('Hosts', (object,), hosts2)

        # If everything goes well, parent can only be an isolated instance.
        # (It's coming from ChildNodeDescriptor through getattr which isolates
        # well, or through a recursive iter_isolations call which should only
        # return isolated instances.)
        assert not parent or parent._node_is_isolated

        return SimpleNodeItem(parent=parent)

    def get_identifiers(node, parent_identifier):
        # The `node` parameter here is one for which the parent is
        # already isolated. This means that the roles are correct
        # and we can iterate through it.
        for i, host in enumerate(node.hosts.filter('host')._all):
            assert isinstance(host, Host)
            if identifier_type == IsolationIdentifierType.INT_TUPLES:
                identifier = (i,)
            elif identifier_type == IsolationIdentifierType.HOST_TUPLES:
                identifier = (host.__class__,)
            elif identifier_type == IsolationIdentifierType.HOSTS_SLUG:
                identifier = (host.slug, )

            yield (parent_identifier + identifier, host)

    # For a normal node, the isolation consists of the parent isolations.
    if node._node_type == NodeTypes.NORMAL:
        if node.parent:
            for index, n in iter_isolations(node.parent, identifier_type):
                yield (index, getattr(n, node._node_name))
        else:
            # A normal node without parent should always be isolated.
            # This is handled by Node.__new__
            assert node._node_is_isolated

            yield ((), node)

    elif node._node_type == NodeTypes.SIMPLE_ARRAY:
        assert node.parent

        for parent_identifier, parent_node in iter_isolations(node.parent, identifier_type):
            new_node = getattr(parent_node, node._node_name)
            for identifier, host in get_identifiers(new_node, parent_identifier):
                yield (identifier, get_simple_node_cell(parent_node, host, identifier[-1]))

    elif node._node_type == NodeTypes.SIMPLE_ONE:
        assert node.parent
        assert len(node.hosts.filter('host')) == 1

        for parent_identifier, parent_node in iter_isolations(node.parent, identifier_type):
            new_node = getattr(parent_node, node._node_name)
            for identifier, host in get_identifiers(new_node, parent_identifier):
                yield (identifier, get_simple_node_cell(parent_node, host, identifier[-1]))

    elif node._node_type == NodeTypes.SIMPLE:
        if node.parent:
            for index, n in iter_isolations(node.parent, identifier_type):
                yield (index, getattr(n, node._node_name))
        else:
            for identifier, host in get_identifiers(node, ()):
                yield (identifier, get_simple_node_cell(None, host, identifier[-1]))


class SimpleNode(Node):
    """
    A ``SimpleNode`` is a ``Node`` which has only one role, named ``host``.
    Multiple hosts can be given for this role, but all of them will be isolated,
    during execution. This allows parallel executing of functions on each 'cell'.
    """
    __metaclass__ = SimpleNodeBase
    _node_type = NodeTypes.SIMPLE

    def host(self):
        if self._node_is_isolated:
            host = self.hosts.filter('host')
            if len(host) != 1:
                raise AttributeError
            return host[0]
        else:
            raise AttributeError
    host._internal = True
    host = property(host)


class Action(object):
    """
    Node actions, which are defined as just functions, will be wrapped into
    this Action class. When one such action is called, this class will make
    sure that a correct ``env`` object is passed into the function as its first
    argument.
    :param node_instance: The Node Env to which this Action is bound.
    :type node_instance: None or :class:`deployer.node.Env`
    """
    def __init__(self, attr_name, node_instance, func, is_property=False, is_query=False, query=None):
        self._attr_name = attr_name
        self._node_instance = node_instance
        self._func = func # TODO: wrap _func in something that checks whether the first argument is an Env instance.
        self.is_property = is_property
        self.is_query = is_query
        self.query = query

    @classmethod
    def from_query(cls, attr_name, node_instance, query):
        # Make a callable from this query.
        def run_query(i, return_query_result=False):
            """
            Handles exceptions properly. -> wrap anything that goes wrong in
            QueryException.
            """
            try:
                if return_query_result:
                    # Return the QueryResult wrapper instead.
                    return query._execute_query(i)
                else:
                    return query._execute_query(i).result

            except Exception as e:
                from deployer.exceptions import QueryException
                raise QueryException(i._node, attr_name, query, e)

        # Make sure that a nice name is passed to Action
        run_query.__name__ = str('query:%s' % query.__str__())

        return cls(attr_name, node_instance, run_query, is_query=True, query=query)

    @classmethod
    def from_property(cls, attr_name, node_instance, func):
        return cls(attr_name, node_instance, func, is_property=True)

    def __repr__(self):
        # Mostly useful for debugging.
        if self._node_instance:
            return '<Action %s.%s>' % (get_node_path(self._node_instance), self._attr_name)
        else:
            return "<Unbound Action %s>" % self._attr_name


    def __call__(self, env, *a, **kw):
        """
        Call this action using the unbound method.
        """
        # Calling an action is normally only possible when it's wrapped by an
        # Env object, then it becomes an EnvAction. When, on the other hand,
        # this Action object is called unbound, with an Env object as the first
        # parameter, we wrap it ourself in an EnvAction object.
        if self._node_instance is None and isinstance(env, Env):
            return env._Env__wrap_action(self)(*a, **kw)
        else:
            raise TypeError('Action is not callable. '
                'Please wrap the Node instance in an Env object first.')

    @property
    def name(self):
        return self._attr_name

    @property
    def node(self):
        return self._node_instance

    @property
    def node_group(self):
        return self._node_instance.node_group or Group()

    @property
    def suppress_result(self):
        return getattr(self._func, 'suppress_result', False)


class EnvAction(object):
    """
    Action wrapped by an Env object.
    Calling this will execute the action in the environment.
    """
    def __init__(self, env, action):
        assert isinstance(env, Env)
        assert isinstance(action, Action)

        self._env = env
        self._action = action

    def __repr__(self):
        return '<Env.Action %s.%s>' % (get_node_path(self._env._node), self._action.name)

    @property
    def name(self):
        return self._action.name

    @property
    def node(self):
        # In an Env, the node is the Env.
        return self._env

    @property
    def suppress_result(self):
        return self._action.suppress_result

    @property
    def is_property(self):
        return self._action.is_property

    @property
    def is_query(self):
        return self._action.is_query

    def _run_on_node(self, isolation, *a, **kw):
        """
        Run the action on one isolation. (On a normal Node, or on a SimpleNode cell.)
        """
        with isolation._logger.group(self._action._func, *a, **kw):
            while True:
                try:
                    return self._action._func(isolation, *a, **kw)
                except ActionException as e:
                    raise
                except ExecCommandFailed, e:
                    isolation._logger.log_exception(e)

                    if self._env._pty.interactive:
                        # If the console is interactive, ask what to do, otherwise, just abort
                        # without showing this question.
                        choice = Console(self._env._pty).choice('Continue?',
                                [ ('Retry', 'retry'),
                                ('Skip (This will not always work.)', 'skip'),
                                ('Abort', 'abort') ], default='abort')
                    else:
                        choice = 'abort'

                    if choice == 'retry':
                        continue
                    elif choice == 'skip':
                        class SkippedTaskResult(object):
                            def __init__(self, node, action):
                                self._node = node
                                self._action = action

                            def __getattribute__(self, name):
                                raise Exception('SkippedTask(%r.%r) does not have an attribute %r' % (
                                        object.__getattr__(self, '_node'),
                                        object.__getattr__(self, '_action'),
                                        name))


                        return SkippedTaskResult(self._env._node, self._action)
                    elif choice == 'abort':
                        # TODO: send exception to logger -> and print it
                        raise ActionException(e, traceback.format_exc())
                except Exception as e:
                    e2 = ActionException(e, traceback.format_exc())
                    isolation._logger.log_exception(e2)
                    raise e2

    def __call__(self, *a, **kw):
        if isinstance(self._env, SimpleNode) and not self._env._node_is_isolated and \
                            not getattr(self._action._func, 'dont_isolate_yet', False):

            # Get isolations of the env.
            isolations = list(self._env)

            # No hosts in SimpleNode. Nothing to do.
            if len(isolations) == 0:
                print 'Nothing to do. No hosts in %r' % self._action
                return [ ]

            # Exactly one host.
            elif len(isolations) == 1:
                return [ self._run_on_node(isolations[0], *a, **kw) ]

            # Multiple hosts, but isolate_one_only flag set.
            elif getattr(self._action._func, 'isolate_one_only', False):
                # Ask the end-user which one to use.
                        # TODO: this is not necessarily okay. we can have several levels of isolation.
                options = [ ('%s    [%s]' % (i.host.slug, i.host.address), i) for i in isolations ]
                i = Console(self._env._pty).choice('Choose a host', options, allow_random=True)
                return self._run_on_node(i, *a, **kw)

            # Multiple hosts. Fork for each isolation.
            else:
                errors = []

                # Create a callable for each host.
                def closure(isolation):
                    def call(pty):
                        # Isolation should be an env, but
                        i2 = Env(isolation._node, pty, isolation._logger, isolation._is_sandbox)

                        # Fork logger
                        logger_fork = self._env._logger.log_fork('On: %r' % i2._node)
                                # TODO: maybe we shouldn't log fork(). Consider it an abstraction.

                        try:
                            # Run this action on the new service.
                            result = self._run_on_node(i2, *a, **kw)

                            # Succeed
                            logger_fork.set_succeeded()
                            return result
                        except Exception as e:
                            # TODO: handle exception in thread
                            logger_fork.set_failed(e)
                            errors.append(e)
                    return call

                # For every isolation, create a callable.
                callables = [ closure(i) for i in isolations ]
                logging.info('Forking %r (%i pseudo terminals)' % (self._action, len(callables)))

                fork_result = self._env._pty.run_in_auxiliary_ptys(callables)
                fork_result.join()

                if errors:
                    # When an error occcured in one fork, raise this error
                    # again in current thread.
                    raise errors[0]
                else:
                    # This returns a list of results.
                    return fork_result.result
        else:
            return self._run_on_node(self._env, *a, **kw)

