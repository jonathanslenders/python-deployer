host_container
==============

Access to hosts from within a :class:`~deployer.node.base.Node` class happens
through a :class:`~deployer.host_container.HostsContainer` proxy. This
container object has also methods for reducing the amount of hosts on which
commands are executed, by filtering according to conditions.

The :attr:`~deployer.node.base.Env.hosts` property of
:class:`~deployer.node.base.Env` wrapper around a node instance returns such a
:class:`~deployer.host_container.HostsContainer` object.

::

    class MyNode(Node):
        class Hosts:
            web_servers = { Host1, Host2 }
            caching_servers = Host3

        def do_something(self):
            # ``self.hosts`` here is a HostsContainer instance.
            self.hosts.filter('caching_servers').run('echo hello')

Reference
---------

.. autoclass:: deployer.host_container.HostsContainer
    :members:

.. autoclass:: deployer.host_container.HostContainer
    :members:
