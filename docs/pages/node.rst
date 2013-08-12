The node object
===============

The `deployer.node.Node` class is probably the most important class of this
framework. See `architecture of roles and nodes
<architecture-of-roles-and-nodes>` for a high level overview of what a Node
exactly is.

A simple example of a node:

::

    from deployer.node import SimpleNode

    class SayHello(SimpleNode):
        def hello(self):
            self.host.run('echo hello world')

.. note:: It is interesting to know that ``self`` is actually not a ``Node`` instance,
      but an ``Env`` object which will proxy this actual Node class. This is
      because there is some metaclass magic going on, which takes care of sandboxing,
      logging and some other nice stuff, that you get for free.

      Except that a few other variables like ``self.console`` are available,
      you normally won't notice anything.


Running the code
----------------

::

    from deployer.node import Env

    env = Env(MyNode())
    env.hello()


.. _node-inheritance:

Inheritance
-----------

A node is meant to be reusable. It is encouraged to inherit from such a node
class and overwrite properties or class members.

Expansion of double underscores
*******************************

The double underscore expansion is a kind of syntactic sugar to make overriding
more readable.

Suppose we already had a node like this:

::

    class WebApp(Node):
        class Nginx(Node):
            class Server(Node):
                domain = 'www.example.com'

Now, we'd like to inherit from ``WebApp``, but change the
``Nginx.Server.domain`` property there to 'mydomain.com'. Normally, in Python,
you do this:

::

    class MyWebApp(WebApp):
        class Nginx(WebApp.Nginx):
            class Server(WebApp.Nginx.Server):
                domain = 'mydomain.com'

This is not too bad, but if you have a lot of nested classes, it can become
pretty ugly. Therefor, the `deployer.node.Node` class has some magic which
allows us to do this instead:

::

    class MyWebApp(WebApp):
        Nginx__Server__domain = 'mydomain.com'

If you'd like, you can also use the same syntax to add function to the inner
classes:

::

    class MyWebApp(WebApp):
        def Nginx__Server__get_full_domain(self):
            # Note that 'self' points to the 'Server' class at this point,
            # not to 'Webapp'!
            return 'http://%s' % self.domain


The difference between Node and SimpleNode
------------------------------------------

TODO: ...


.Array and .JustOne
*******************

TODO: complete ...

TODO: ``SimpleNode`` will probably be renamed to ``PNode`` (or ParallelNode)

``.Array`` and ``.JustOne`` are required for nesting a ``SimpleNode`` inside a
normal ``Node``. The idea is that when host roles are mapped from the parent
``Node``, to the child -- which is a ``SimpleNode`` --, that this childnode
behaves as an array. Each 'cell' in the array is isolated, so it's possible to
execute a command on just one 'cell' (or host) of the array or all 'cells' (or
hosts.) You can use it as follows:

::

    class NormalNode(Node):
        class OurSimpleNode(SimpleNode.Array):
            class SimpleNode(SimpleNode):
                pass


Basically, you can nest 'normal' nodes inside each other, and
``SimpleNodes`` classes inside each other. However, when nesting such a
``SimpleNode`` inside a normal node, the ``.Array`` suffix is required to
indicate the creation of an array. ``.JustOne`` can always be used instead of
an array, if you assert that only one host will be in there.

TODO: more examples...


Using contrib.nodes
-------------------

The deployer framework is delivered with a `contrib.nodes` directory which
contains nodes that should be generic enough to be usable by a lot of people.
Even if you can't use them in your case, they may be good examples of how to do
certain things. So don't be afraid to look at the source code, you can learn some
good practices there. Take these and inherit as you want to, or start from
scratch if you prefer that way.

Some recommended contrib nodes:

 - `deployer.contrib.nodes.config.Config`

   This a the base class that we are using for every configuration file. It is
   very useful for when you are automatically generating server configurations
   according to specific deployment configurations. Without any efford, this
   class will allow you to do diff's between your new, generated config, and
   the config that's currently on the server side.


Reference
---------

.. automodule:: deployer.node
    :members:
