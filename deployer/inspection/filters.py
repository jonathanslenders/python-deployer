__doc__ = \
"""
Filters for NodeIterator
------------------------

``NodeIterator`` is the iterator that ``Inspector.walk()`` returns. It supports
filtering to limit the yielded nodes according to certain conditions.

A filter is a ``Filter`` instance or an AND or OR operation of several
filters. For instance:

::

    from deployer.inspection.filters import HasAction, PublicOnly
    Inspector(node).walk(HasAction('my_action') & PublicOnly & ~ InGroup(Staging))
"""

__all__ = (
        'Filter',
        'PublicOnly',
        'PrivateOnly',
        'IsInstance',
        'HasAction',
        'InGroup',
)

from deployer.groups import Group


class Filter(object):
    """
    Base class for ``Inspector.walk`` filters.
    """
    def _filter(self):
        raise NotImplementedError

    def __and__(self, other_filter):
        return AndFilter(self, other_filter)

    def __or__(self, other_filter):
        return OrFilter(self, other_filter)

    def __invert__(self):
        return NotFilter(self)


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


class NotFilter(Filter):
    def __init__(self, filter1):
        self.filter1 = filter1

    def _filter(self, node):
        return not self.filter1._filter(node)

    def __repr__(self):
        return '~ %r' % self.filter1


class _PublicOnly(Filter):
    def _filter(self, node):
        return not (node._node_name and node._node_name.startswith('_'))

    def __repr__(self):
        return 'PublicOnly'

PublicOnly = _PublicOnly()
"""
Filter on public nodes.
"""


class _PrivateOnly(Filter):
    def _filter(self, node):
        return node._node_name and node._node_name.startswith('_')

    def __repr__(self):
        return 'PrivateOnly'

PrivateOnly = _PrivateOnly()
"""
Filter on private nodes.
"""


class IsInstance(Filter):
    """
    Filter on the nodes which are an instance of this ``Node`` class.

    :param node_class: A :class:`deployer.node.Node` subclass.
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


class InGroup(Filter):
    """
    Filter nodes that are in this group.

    :param group: A :class:`deployer.groups.Group` subclass.
    """
    def __init__(self, group):
        assert issubclass(group, Group)
        self.group = group

    def _filter(self, node):
        from deployer.inspection.inspector import Inspector
        return Inspector(node).get_group() == self.group

    def __repr__(self):
        return 'InGroup(%r)' % self.group
