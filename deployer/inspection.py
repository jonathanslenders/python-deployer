from deployer.node import SimpleNode, Node, Env, IsolationIdentifierType, iter_isolations, Action, Group

__all__ = (
    'Inspector',
)

class PathType:
    """
    Options for Inspector.get_path()
    """
    NAME_ONLY = 'NAME_ONLY'
    NODE_AND_NAME = 'NODE_AND_NAME'
    NODE_ONLY = 'NODE_ONLY'


class Inspector(object):
    """
    Introspection of a Node object.
    """
    def __init__(self, node):
        if isinstance(node, Env):
            self.env = node
            self.node = node._node
            self.__class__ = _EnvInspector
        elif isinstance(node, Node):
            self.env = None
            self.node = node
        else:
            raise Exception('Expecting a Node or Env instance')

    def __repr__(self):
        return 'Inspector(node=%s)' % self.node.__class__.__name__

    @property
    def is_isolated(self):
        return self.node._node_is_isolated

    def iter_isolations(self, identifier_type=IsolationIdentifierType.INT_TUPLES):
        return iter_isolations(self.node, identifier_type=identifier_type)

    def get_isolation(self, identifier, identifier_type=IsolationIdentifierType.INT_TUPLES):
        for i, node in self.iter_isolations(identifier_type):
            if i == identifier:
                return node
        raise AttributeError('Isolation not found')

    def _filter(self, include_private, filter):
        childnodes = []
        for name in dir(self.node.__class__):
            if not name.startswith('__') and name != 'parent':
                if include_private or not name.startswith('_'):
                    attr = getattr(self.node, name)
                    if filter(attr):
                        childnodes.append(attr)
        return childnodes

    def get_childnodes(self, include_private=True, verify_parent=True):
        """
        Return a list of childnodes.
        include_private: ignore names starting with underscore.
        verify_parent: check the parent pointer.
        """
        # TODO: order by _node_creation_counter
        def f(i):
            return isinstance(i, Node) and (not verify_parent or i.parent == self.node)
        return self._filter(include_private, f)

    def has_childnode(self, name):
        try:
            self.get_childnode(name)
            return True
        except AttributeError:
            return False

    def get_childnode(self, name):
        for c in self.get_childnodes():
            if Inspector(c).get_name() == name:
                return c
        raise AttributeError('Childnode not found.')

    def get_actions(self, include_private=True):
        return self._filter(include_private, lambda i: isinstance(i, Action) and not i.is_property)

    def has_action(self, name):
        try:
            self.get_action(name)
            return True
        except AttributeError:
            return False

    def get_action(self, name):
        for a in self.get_actions():
            if a.name == name:
                return a
        raise AttributeError('Action not found.')

    def supress_result_for_action(self, name):
        return getattr(self.get_actions(name), 'supress_result', False)

    def get_path(self, path_type=PathType.NAME_ONLY):
        """
        Return a (name1, name2, ...) tuple, defining the path from the root until here.
        """
        result = []
        n = self.node
        while n:
            if path_type == PathType.NAME_ONLY:
                result.append(Inspector(n).get_name())

            elif path_type == PathType.NODE_AND_NAME:
                result.append((n, Inspector(n).get_name()))

            elif path_type == PathType.NODE_ONLY:
                result.append(n)
            else:
                raise Exception('Invalid path_type')

            n = n.parent

        return tuple(result[::-1])

    def get_root(self):
        """
        Return the root node of the tree.
        """
        node = self.node
        while node.parent:
            node = node.parent
        return node

    def get_group(self):
        """
        Return the group to which this node belongs.
        """
        return self.node.node_group or (
                Inspector(self.node.parent).get_group() if self.node.parent else Group())

    def get_name(self):
        return self.node._node_name or self.node.__class__.__name__

    def get_full_name(self):
        return self.node.__class__.__name__

    def get_isolation_identifier(self):
        return self.node._node_isolation_identifier

    def is_callable(self):
        return hasattr(self.node, '__call__')

    def _walk(self):
        visited = set()
        todo = [ self.node ]

        def key(n):
            # Unique identifier for every node.
            # (The childnode descriptor will return another instance every time.)
            i = Inspector(n)
            return (i.get_root(), i.get_path())

        while todo:
            n = todo.pop(0)
            yield n
            visited.add(key(n))

            for c in Inspector(n).get_childnodes(verify_parent=False):
                if key(c) not in visited:
                    todo.append(c)

    def walk(self, public_only=False):
        """
        Recursively walk (topdown) through the nodes and yield them.

        It does not yet isolate SimpleNodes in several nodes.
        """
        return NodeIterator(self._walk).public_only(public_only)


class _EnvInspector(Inspector):
    """
    When doing the introspection on an Env object, this acts like a proxy and
    makes sure that the result is compatible for in an Env environment.
    """
    def get_childnodes(self, include_private=True):
        nodes = Inspector.get_childnodes(self, include_private)
        return map(self.env._Env__wrap_node, nodes)

    def get_childnode(self, name):
        for c in self.get_childnodes():
            if Inspector(c).get_name() == name:
                return c
        raise AttributeError('Childnode not found.')

    def get_actions(self, include_private=True):
        actions = []
        for a in Inspector.get_actions(self, include_private):
            actions.append(self.env._Env__wrap_action(a))
        return actions

    def iter_isolations(self, *a, **kw):
        for index, node in Inspector.iter_isolations(self, *a, **kw):
            yield index, self.env._Env__wrap_node(node)

    def _walk(self):
        for node in Inspector._walk(self):
            yield self.env._Env__wrap_node(node)



class NodeIterator(object):
    """
    Generator object which yields the nodes in a collection.
    """
    def __init__(self, node_iterator_func):
        self._iterator_func = node_iterator_func

    def __iter__(self):
        return self._iterator_func()

    def __len__(self):
        return sum(1 for _ in self)

    def filter(self, node_class):
        """
        Filter on the nodes of type node_class. Node_class can be a Node
        subclass or tuple of Node classes.
        """
        def new_iterator():
            for n in self:
                if isinstance(n, node_class):
                    yield n
        return NodeIterator(new_iterator)

    def filter_on_action(self, name):
        """
        Filter on the nodes which implement this action.
        """
        def new_iterator():
            for n in self:
                if Inspector(n).has_action(name):
                    yield n
        return NodeIterator(new_iterator)

    def public_only(self, public_only=True):
        """
        Filter only public nodes.
        """
        if not public_only:
            # Shortcut, no need to filter
            return self
        def new_iterator():
            for n in self:
                if not n._node._node_name or not n._node._node_name.startswith('_'):
                    yield n
        return NodeIterator(new_iterator)

    def prefer_isolation(self, index):
        """
        For nodes that are not yet isoleted. (SimpleNodes, or normal Nodes
        nested in there.) yield the isolations with this index.  Otherwise,
        nodes are yielded unmodified.
        """
        def new_iterator():
            for n in self:
                # When this is a SimpleNode, yield only this isolation if it
                # exists.
                if not n._node_is_isolated:
                    try:
                        yield n[index]
                    except KeyError:
                        # TODO: maybe: yield n here not 100% sure, whether this is the best.
                        pass
                # Otherwise, just yield the node.
                else:
                    yield n
        return NodeIterator(new_iterator)

    def call_action(self, name, *a, **kw):
        """
        Call a certain action on all the nodes.

        This will split the SimpleNode Arrays into their isolations.
        """
        for n in self:
            for index, node in Inspector(n).iter_isolations():
                action = getattr(node, name)
                yield action(*a, **kw)
