from deployer.node import Node, Env, IsolationIdentifierType, iter_isolations, Action, Group

__all__ = (
    'Inspector',
)

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

    def iter_isolations(self, identifier_type=IsolationIdentifierType.INT_TUPLES):
        return iter_isolations(self.node, identifier_type=identifier_type)

    def _filter(self, include_private, filter):
        childnodes = []
        for name in dir(self.node.__class__):
            if not name.startswith('__'):
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

    def get_path(self):
        """
        Return a (name1, name2, ...) tuple, defining the path from the root until here.
        """
        result = []
        n = self.node
        while n:
            result.append(Inspector(n).get_name())
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

    def is_callable(self):
        return hasattr(self.node, '__call__')

    def walk(self):
        """
        Recursively walk (topdown) through the nodes and yield them.
        """
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
        # TODO: determine first a clean API for what this function should return.
        raise NotImplementedError

    def get_action(self, name):
        raise NotImplementedError

    def iter_isolations(self, *a, **kw):
        for index, node in Inspector.iter_isolations(self, *a, **kw):
            yield index, self.env._Env__wrap_node(node)

    def walk(self, *a, **kw):
        for node in Inspector.walk(self, *a, **kw):
            yield self.env._Env__wrap_node(node)