host_container
==============

Access to hosts from within a ``Node`` class happens through a
``HostsContainer`` proxy. This container object has also methods for reducing
the amount of hosts on which commands are executed, by filtering according to
conditions.

The ``hosts`` property of a node instance returns such a ``HostsContainer``
object.

::

    class MyNode(Node):
        class Hosts:
            web_servers = [Host1, Host2]
            caching_servers = Host3

        def do_something(self):
            # self.hosts here, is a HostsContainer instance.
            self.hosts.filter('caching_servers').run('echo hello')

Reference
---------

.. automodule:: deployer.host_container
    :members:

