from deployer.utils import isclass
from deployer.host_container import HostsContainer

__all__ = ('ALL_HOSTS', 'map_roles', 'DefaultRoleMapping', )


class _MappingFilter(object):
    def __init__(self, name):
        self._name = name

    def __repr__(self):
        return self._name


ALL_HOSTS = _MappingFilter('ALL_HOSTS')
"""
Constant to indicate in a role mapping that all hosts of the parent should be
mapped to this role.
"""


class RoleMapping(object):
    """
    A role mapping defines which hosts from a parent Node will used in the childnode,
    and for which roles.
    Some examples:

    ::

        @map_roles(role='parent_role', role2=('parent_role2', 'parent_role3'))
        @map_roles(role='parent_role', role2=ALL_HOSTS)

        # If you don't define any role names, they'll map to the name 'host'.
        @map_roles('parent_role', 'another_parent_role')

        # This will map all the hosts in all the roles of the parent node, to the
        # role named 'host' in this node.
        @map_roles(ALL_HOSTS)
    """
    def __init__(self, *host_mapping, **mappings):
        # Validate first
        for v in host_mapping:
            assert isinstance(v, (basestring, _MappingFilter)), TypeError('Invalid parameter: %s' % v)

        for k, v in mappings.items():
            assert isinstance(v, (basestring, tuple, _MappingFilter)), TypeError('Invalid parameter: %s' % v)

            # Make sure that all values are tuples.
            if isinstance(v, basestring):
                mappings[k] = (v,)

        if host_mapping:
            mappings = dict(host=host_mapping, **mappings)

        self._mappings = mappings # Maps role -> tuple of role names.

    def __call__(self, node_class):
        from deployer.node import Node
        if not isclass(node_class) or not issubclass(node_class, Node):
            raise TypeError('Role mapping decorator incorrectly applied. '
                            '%r is not a Node class' % node_class)

        # Apply role mapping on a copy of the node class.
        return type(node_class.__name__, (node_class, ), {
                    'Hosts': self,
                    # Keep the module, to make sure that inspect.getsourcelines still works.
                    '__module__': node_class.__module__,
                    })

    def apply(self, parent_node_instance):
        """
        Map roles from the parent to the child node and create a new
        :class:`HostsContainer` instance by applying it.
        """
        parent_container = parent_node_instance.hosts
        def get(f):
            if f == ALL_HOSTS:
                return parent_container.get_hosts()
            else:
                assert isinstance(f, tuple), TypeError('Invalid value found in mapping: %r' % f)
                return parent_container.filter(*f).get_hosts()

        return HostsContainer({ role: get(f) for role, f in self._mappings.items() },
                    pty=parent_container._pty,
                    logger=parent_container._logger,
                    is_sandbox=parent_container._sandbox)


map_roles = RoleMapping


class DefaultRoleMapping(RoleMapping):
    """
    Default mapping: take the host container from the parent.
    """
    def apply(self, parent_node_instance):
        return parent_node_instance.hosts

