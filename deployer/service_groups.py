class Group(object):
    """
    Group to which a setup belongs.
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
    Set the group for this service.

    >> @set_group(Group)
    >> class MyService(Service):
    >>     pass

    This is equivalent to.

    >> class MyService(Service):
    >>     class Meta(Service.Meta):
    >>         group = Group
    """
    def group_setter(service):
        # First, we create a new Meta type, where we override the group.
        new_meta = type('Meta', (service.Meta, ), { 'group': group })

        # Then, we create a new service type, where we replace the meta type.
        # So, note that we don't monkey patch, but create new class
        # definitions instead. (This we way avoid any side effects, in case
        # the class would elsewhere still be used.)
        return type(service.__name__, (service,), { 'Meta': new_meta })
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
