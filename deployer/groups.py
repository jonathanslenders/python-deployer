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

    # Color for this service/action in the shell.
    color = None


def set_group(group):
    """
    Set the group for this node.

    >> @set_group(Group)
    >> class MyNode(Node):
    >>     pass

    This is equivalent to.

    >> class MyNode(Node):
    >>     node_group = Group
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
