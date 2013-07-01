__doc__ = \
"""
Filters for NodeIterator
------------------------

The iterator that ``Inspector.walk()`` returns, can be filtered to limit the
yielded nodes according to certain conditions.

A filter is a Filter instance or an AND or OR operation of several
filters.

Example usage:

::
    from deployer.inspection.filters import HasAction, PublicOnly
    Inspector(node).walk(HasAction('my_action') & PublicOnly)
"""

__all__ = (
        'PublicOnly',
        'PrivateOnly',
        'IsInstance',
        'HasAction',
)


class Filter(object):
    def _filter(self):
        raise NotImplementedError

    def __and__(self, other_filter):
        return AndFilter(self, other_filter)

    def __or__(self, other_filter):
        return OrFilter(self, other_filter)


class AndFilter(Filter):
    def __init__(self, filter1, filter2):
        self.filter1 = filter1
        self.filter2 = filter2

    def _filter(self, node):
        return self.filter1._filter(node) and self.filter2._filter(node)

    def __repr__(self):
        return '%r & %r' % (self.filter1, self.filter2)


class OrFilter(Filter):
    def __init__(self, filter1, filter2):
        self.filter1 = filter1
        self.filter2 = filter2

    def _filter(self, node):
        return self.filter1._filter(node) or self.filter2._filter(node)

    def __repr__(self):
        return '%r | %r' % (self.filter1, self.filter2)


class _PublicOnly(Filter):
    """
    Filter on public nodes.
    """
    def _filter(self, node):
        return not (node._node_name and node._node_name.startswith('_'))

    def __repr__(self):
        return 'PublicOnly'

PublicOnly = _PublicOnly()


class _PrivateOnly(Filter):
    """
    Filter on private nodes.
    """
    def _filter(self, node):
        return node._node_name and node._node_name.startswith('_')

    def __repr__(self):
        return 'PrivateOnly'

PrivateOnly = _PrivateOnly()


class IsInstance(Filter):
    """
    Filter on the nodes which are an instance of this Node class.
    """
    def __init__(self, node_class):
        self.node_class = node_class

    def _filter(self, node):
        return isinstance(node, self.node_class)

    def __repr__(self):
        return 'IsInstance(%r)' % self.node_class


class HasAction(Filter):
    """
    Filter on the nodes which implement this action.
    """
    def __init__(self, action_name):
        self.action_name = action_name

    def _filter(self, node):
        from deployer.inspection.inspector import Inspector
        return Inspector(node).has_action(self.action_name)

    def __repr__(self):
        return 'HasAction(%r)' % self.action_name
