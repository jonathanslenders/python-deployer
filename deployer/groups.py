
__doc__ = \
"""
A ``Group`` can be attached to every Node, in order to put them in categories.

Typically, you have group names like ``alpha``, ``beta`` and ``production``.
The interactive shell will show the nodes in other colours, depending on the
group they're in.

For instance.

::

    from deployer.groups import production, staging

    class N(Node):
        @production
        class Child(Node):
            pass
"""

__all__ = (
        'Group',
        'set_group'
)

class Group(object):
    """
    Group to which a node belongs.
    """
    class __metaclass__(type):
        def __new__(cls, name, bases, dct):
            # Give the group a 'name'-property, based on
            # its own class name
            dct['name'] = name
            return type.__new__(cls, name, bases, dct)

    color = None
    """
    Colour for this service/action in the shell. Right now, only the colours
    from the ``termcolor`` library are supported:

    grey, red, green, yellow, blue, magenta, cyan, white
    """


def set_group(group):
    """
    Set the group for this node.

    ::

        @set_group(Staging)
        class MyNode(Node):
            pass
    """
    def group_setter(node):
        return type(node.__name__, (node,), { 'node_group': group })
    return group_setter

#
# Built-in groups
#

class Production(Group):
    color = 'red'

class Staging(Group):
    color = 'yellow'

class Beta(Group):
    color = 'green'

class Local(Group):
    color = 'green'

class Other(Group):
    color = 'white'

class Utility(Group):
    color = 'magenta'

#
# Decorators for built-in groups
#

production = set_group(Production)
staging = set_group(Staging)
beta = set_group(Beta)
local = set_group(Local)
other = set_group(Other)
utility = set_group(Utility)
