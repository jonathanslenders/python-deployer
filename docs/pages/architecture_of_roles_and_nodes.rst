.. _architecture-of-roles-and-nodes:

Architecture of roles and nodes
===============================

Use cases
---------

Before we go in depth, let's first look at a typical set-up of a web server.
The following picture displays serveral connected components. It contains a web
server connected to some database back-ends, and a load balancer in front of
it. Every component appears exactly once.

.. graphviz::

   digraph web_components {
       "Load balancer" -> "Web server";
       "Web server" -> "Master database";
       "Web server" -> "Slave database";
       "Web server" -> "Caching";
       "Web server" -> "Queue";
       "Master database" -> "Slave database";
   }

Now we are going to scale. If we triple the amount of web servers, and put an
extra load balancer in front of our system. We end up with many more arrows.

.. graphviz::

   digraph web_components {
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
           label="Local";
           "ws 0" -> "db 0";
           "ws 0" -> "c 0";
           "ws 0" -> "q 0";
      }
      subgraph cluster1 {
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
           label="Staging";
           "lb 2" -> "ws 2";
           "ws 2" -> "master db 2";
           "ws 2" -> "slave db 2";
           "ws 2" -> "c 2";
           "ws 2" -> "q 2";
           "master db 2" -> "slave db 2";
      }
      subgraph cluster3 {
           label="Production";
           "lb 3" -> "ws 3";
           "lb 3" -> "ws 4";
           "lb 3" -> "ws 5";
           "lb 4" -> "ws 3";
           "lb 4" -> "ws 3";
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

Now we are going to create `deployer.node.Node` classes. A Node is probably the
most important class in this framework, because basically all deployment code
is structured in node. Every circle in the above diagrams can be considered a
node.

So we are going to write a script that contains all these connected parts or
nodes.  Basically, it's one container node, and childnodes for all the
components that we have. As an example, we also add the ``Git`` component that
we use for transferring our code and media to the servers.

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

The idea is that if we create instances of ``WebSystem`` here, we are only
going to tell the root node which roles map to which hosts. We use inheritance
to override the ``WebSystem`` node and add ``Hosts`` to the derived classes.
Wrapping it in ``RootNode`` is not really necassary, but cool to group these if
we'd put an interactive shell around it.

::

    class RootNode(Node):
        class StagingSystem(WebSystem):
            class Hosts:
                load_balancer= [ StagingHost0 ]
                web = [ StagingHost0  ]
                master_db = [ StagingDB ]
                slave_db = [ ] # If empty, this line can be left away.
                queue = [ StagingHost0 ]
                cache = [ StagingHost0 ]

        class ProductionSystem(WebSystem):
            class Hosts:
                load_balancer= [ LB0, LB1 ]
                web = [ WebServer1, WebServer2, WebServer3 ]
                master_db = [ MasterDB ]
                slave_db = [ SlaveDB ]
                queue = [ QueueHost ]
                cache = [ CacheHost ]

Now it's up to the framework to the figure out which hosts belong to which
childnodes. With a little help of the ``role_mapping`` decorator, that's
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

