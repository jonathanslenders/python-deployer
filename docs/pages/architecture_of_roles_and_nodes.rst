.. _architecture-of-roles-and-nodes:

Architecture of roles and nodes
===============================

In this chapter, we go a little more in depth on what a
:class:`Node <deployer.node.Node>` really is.

Use cases
---------

Before we go in depth, let's first look at a typical set-up of a web server.
The following picture displays serveral connected components. It contains a web
server connected to some database back-ends, and a load balancer in front of
it. Every component appears exactly once.

.. graphviz::

   digraph web_components {
       "Load balancer" [style=filled, fillcolor=darkorchid1];
       "Web server" [style=filled, fillcolor=darkolivegreen1];
       "Cache" [style=filled, fillcolor=gold1];
       "Queue" [style=filled, fillcolor=pink1];
       "Master database" [style=filled, fillcolor=steelblue1];
       "Slave database" [style=filled, fillcolor=cadetblue1];

       "Load balancer" -> "Web server";
       "Web server" -> "Master database";
       "Web server" -> "Slave database";
       "Web server" -> "Cache";
       "Web server" -> "Queue";
       "Master database" -> "Slave database";
   }

Now we are going to scale. If we triple the amount of web servers, and put an
extra load balancer in front of our system. We end up with many more arrows.

.. graphviz::

   digraph web_components {
       "Load balancer 1" [style=filled, fillcolor=darkorchid1];
       "Load balancer 2" [style=filled, fillcolor=darkorchid1];
       "Web server 1" [style=filled, fillcolor=darkolivegreen1];
       "Web server 2" [style=filled, fillcolor=darkolivegreen1];
       "Web server 3" [style=filled, fillcolor=darkolivegreen1];
       "Cache" [style=filled, fillcolor=gold1];
       "Queue" [style=filled, fillcolor=pink1];
       "Master database" [style=filled, fillcolor=steelblue1];
       "Slave database" [style=filled, fillcolor=cadetblue1];

       "Load balancer 1" -> "Web server 1";
       "Load balancer 1" -> "Web server 2";
       "Load balancer 1" -> "Web server 3";
       "Load balancer 2" -> "Web server 1";
       "Load balancer 2" -> "Web server 2";
       "Load balancer 2" -> "Web server 3";
       "Web server 1" -> "Master database";
       "Web server 1" -> "Slave database";
       "Web server 1" -> "Cache";
       "Web server 1" -> "Queue";
       "Web server 2" -> "Master database";
       "Web server 2" -> "Slave database";
       "Web server 2" -> "Cache";
       "Web server 2" -> "Queue";
       "Web server 3" -> "Master database";
       "Web server 3" -> "Slave database";
       "Web server 3" -> "Cache";
       "Web server 3" -> "Queue";
       "Master database" -> "Slave database";
   }


It's even possible that we have several instaces of all this. A local
development set-up, a test server, a staging server, and a production server.
Let's see:

.. graphviz::

    digraph G {
      compound=true;
      subgraph cluster_local {
           "ws 0" [style=filled, fillcolor=darkolivegreen1];
           "c 0" [style=filled, fillcolor=gold1];
           "q 0" [style=filled, fillcolor=pink1];
           "db 0" [style=filled, fillcolor=steelblue1];

           label="Local";
           "ws 0" -> "db 0";
           "ws 0" -> "c 0";
           "ws 0" -> "q 0";
      }
      subgraph cluster1 {
           "lb 1" [style=filled, fillcolor=darkorchid1];
           "ws 1" [style=filled, fillcolor=darkolivegreen1];
           "c 1" [style=filled, fillcolor=gold1];
           "q 1" [style=filled, fillcolor=pink1];
           "master db 1" [style=filled, fillcolor=steelblue1];
           "slave db 1" [style=filled, fillcolor=steelblue1];

           label="Testing";
           "lb 1" -> "ws 1";
           "ws 1" -> "master db 1";
           "ws 1" -> "slave db 1";
           "ws 1" -> "c 1";
           "ws 1" -> "q 1";
           "master db 1" -> "slave db 1";
      }
    }

.. graphviz::

    digraph G2 {
      compound=true;
      subgraph cluster2 {
           "lb 2" [style=filled, fillcolor=darkorchid1];
           "ws 2" [style=filled, fillcolor=darkolivegreen1];
           "c 2" [style=filled, fillcolor=gold1];
           "q 2" [style=filled, fillcolor=pink1];
           "master db 2" [style=filled, fillcolor=steelblue1];
           "slave db 2" [style=filled, fillcolor=steelblue1];

           label="Staging";
           "lb 2" -> "ws 2";
           "ws 2" -> "master db 2";
           "ws 2" -> "slave db 2";
           "ws 2" -> "c 2";
           "ws 2" -> "q 2";
           "master db 2" -> "slave db 2";
      }
      subgraph cluster3 {
           "lb 3" [style=filled, fillcolor=darkorchid1];
           "lb 4" [style=filled, fillcolor=darkorchid1];
           "ws 3" [style=filled, fillcolor=darkolivegreen1];
           "ws 4" [style=filled, fillcolor=darkolivegreen1];
           "ws 5" [style=filled, fillcolor=darkolivegreen1];
           "c 3" [style=filled, fillcolor=gold1];
           "q 3" [style=filled, fillcolor=pink1];
           "master db 3" [style=filled, fillcolor=steelblue1];
           "slave db 3" [style=filled, fillcolor=steelblue1];

           label="Production";
           "lb 3" -> "ws 3";
           "lb 3" -> "ws 4";
           "lb 3" -> "ws 5";
           "lb 4" -> "ws 3";
           "lb 4" -> "ws 4";
           "lb 4" -> "ws 5";
           "ws 3" -> "master db 3";
           "ws 3" -> "slave db 3";
           "ws 3" -> "c 3";
           "ws 3" -> "q 3";
           "ws 4" -> "master db 3";
           "ws 4" -> "slave db 3";
           "ws 4" -> "c 3";
           "ws 4" -> "q 3";
           "ws 5" -> "master db 3";
           "ws 5" -> "slave db 3";
           "ws 5" -> "c 3";
           "ws 5" -> "q 3";
           "master db 3" -> "slave db 3";
      }
    }

Obviously we don't want to write 4 different deployment scripts. The components
are exacty the same every time, the only difference is that the amount of how
many times a certain component appears is not always the same.

In this example, we can identify 4 roles:

- Load balancer
- Cache server
- Queue server
- Master database
- slave database


Creating nodes.
---------------

Now we are going to create :class:`Node <deployer.node.Node>` classes. A Node
is probably the most important class in this framework, because basically all
deployment code is structured in node. Every circle in the above diagrams can
be considered a node.

So we are going to write a script that contains all these connected parts or
nodes.  Basically, it's one container node, and childnodes for all the
components that we have. As an example, we also add the ``Git`` component where
we'll put in the commands for checking the web server code out from our version
control system.

::

    from deployer.node import Node

    class WebSystem(Node):
        class Cache(Node):
            pass

        class Queue(Node):
            pass

        class LoadBalancer(Node):
            pass

        class Database(Node):
            pass

        class Git(Node):
            pass

The idea is that if we create multiple instances of ``WebSystem`` here, we only
have to tell the root node which roles map to which hosts. We can use
inheritance to override the ``WebSystem`` node and add ``Hosts`` to the derived
classes.  Wrapping it in ``RootNode`` is not really necassary, but cool to
group these if we'd put an interactive shell around it.

::

    class RootNode(Node):
        class StagingSystem(WebSystem):
            class Hosts:
                load_balancer= [ StagingHost0 ]
                web = [ StagingHost0  ]
                master_db = [ StagingHost0 ]
                slave_db = [ ] # If empty, this line can be left away.
                queue = [ StagingHost0 ]
                cache = [ StagingHost0 ]

        class ProductionSystem(WebSystem):
            class Hosts:
                load_balancer = [ LB0, LB1 ]
                web = [ WebServer1, WebServer2, WebServer3 ]
                master_db = [ MasterDB ]
                slave_db = [ SlaveDB ]
                queue = [ QueueHost ]
                cache = [ CacheHost ]

Note that on the staging system, the same physical host is assigned to all the
roles. That's fine: the web server can also act as load balancer, as well as a
cache or queue server. On the production side, we separate them on different
machines.

Now it's up to the framework to the figure out which hosts belong to which
childnodes. With a little help of the ``map_roles`` decorator, that's
possible. We adjust the original ``WebSystem`` node as follows:

::

    from deployer.node import Node, map_roles

    class WebSystem(Node):
        """
        roles: cache, queue, master_db, slave_db, web.
        """
        @map_roles(host='cache')
        class Cache(Node):
            pass

        @map_roles(host='queue')
        class Queue(Node):
            pass

        @map_roles(host='queue')
        class LoadBalancer(Node):
            pass

        @map_roles(master='master_db', slave='slave_db')
        class Database(Node):
            pass

        @map_roles(host=['www', 'load_balancer', 'queue'])
        class Git(Node):
            def checkout(self, commit):
                self.hosts.run('git checkout %s' % commit)

``@map_roles`` needs a list of keyword arguments. The value can be either a
``string`` or ``list`` and decribes the roles of the parent node, and the key
tells the new role in the child node to which these hosts are assigned.

If we now type ``self.hosts.run('shell command')`` in for instance the
``Database`` child node, it will only run in the hosts assigned there. In the
case of our ``ProductionSystem`` above, that's on ``MasterDB`` and ``SlaveDB``.
In the case of ``Git.checkout`` above, the run-command will execute on all
hosts that were mapped to the role ``host``.


More complete example
----------------------

Below, we present a more complete example with real actions like ``start`` and
``stop``. The queue, the cache and the database, they have some methods in
common, -- in fact they are all upstart services --, so therefor we created a
base class ``UpstartService`` that handles the common parts.

::

    #!/usr/bin/env python
    from deployer.node import Node, map_roles, required_property
    from deployer.utils import esc1

    from our_nodes import StagingHost0, LB0, LB1, WebServer1, WebServer2, \
            WebServer3, MasterDB, SlaveDB, QueueHost, CacheHost

    class UpstartService(Node):
        """
        Abstraction for any upstart service with start/stop/status methods.
        """
        name = required_property()

        def start(self):
            self.hosts.sudo('service %s start' % esc1(self.name))

        def stop(self):
            self.hosts.sudo('service %s stop' % esc1(self.name))

        def status(self):
            self.hosts.sudo('service %s status' % esc1(self.name))

    class WebSystem(Node):
        """
        The base definition of our web system.

        roles: cache, queue, master_db, slave_db, web.
        """
        @map_roles(host='cache')
        class Cache(UpstartService):
            name = 'redis'

        @map_roles(host='queue')
        class Queue(UpstartService):
            name = 'rabbitmq'

        @map_roles(host='queue')
        class LoadBalancer(Node):
            # ...
            pass

        @map_roles(master='master_db', slave='slave_db')
        class Database(UpstartService):
            name = 'postgresql'

        @map_roles(host=['www', 'load_balancer', 'queue'])
        class Git(Node):
            def checkout(self, commit):
                self.hosts.run('git checkout %s' % esc1(commit))

            def show(self):
                self.hosts.run('git show')

    class RootNode(Node):
        """
        The root node of our configuration, containing two 'instances' of
        `WebSystem`,
        """
        class StagingSystem(WebSystem):
            class Hosts:
                load_balancer = [ StagingHost0 ]
                web = [ StagingHost0  ]
                master_db = [ StagingHost0 ]
                slave_db = [ ] # If empty, this line can be left away.
                queue = [ StagingHost0 ]
                cache = [ StagingHost0 ]

        class ProductionSystem(WebSystem):
            class Hosts:
                load_balancer = [ LB0, LB1 ]
                web = [ WebServer1, WebServer2, WebServer3 ]
                master_db = [ MasterDB ]
                slave_db = [ SlaveDB ]
                queue = [ QueueHost ]
                cache = [ CacheHost ]

    if __name__ == '__main__':
        start(RootNode)


So, in this example, if ``Staginghost0``, ``LB0`` and the others were real
:class:`deployer.host.Host` definitions, we could start
:ref:`an interactive shell <interactive-shell>`. Then we could for instance
navigate to the database of the production system, by typing
"``cd ProductionSystem Database``" and then "``start``" to execute the command.





