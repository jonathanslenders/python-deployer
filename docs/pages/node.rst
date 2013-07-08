The node object
===============

TODO: examples and documentation.



Inheritance
-----------

A node is meant to be reusable. It is encouraged to inherit from such a node
class and overwrite properties or class members.

Expansion of double underscores
*******************************

TODO: ...

Using contrib.nodes
*******************

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
