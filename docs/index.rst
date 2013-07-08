.. python-deploy-framework documentation master file, created by
   sphinx-quickstart on Thu Jun 20 22:12:13 2013.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Python-deploy-framework
=======================

A Python framework for automatic application deployment on Posix systems.

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

Key features are:

 - Interactive execution of remote commands.
 - Parallel execution.
 - Reusability of all deployment code.

Getting started
===============

Install the framework as follows:

::

    pip install deployer


Hello world
-----------

As a quick example, we create a simple node, which does nothing, except
printing `hello world`, by executing the `echo` command.

::

    from deployer.node import SimpleNode

    class SayHello(SimpleNode):
        def update(self):
            self.host.run('echo hello world')

When `AptGet.install` is called in the example above, it will install the
packages on all the hosts that are known in this Node.

.. note:: It is interesting to know that ``self`` is actually not a ``Node`` instance,
      but an ``Env`` object which will proxy this actual Node class. This is
      because there is some metaclass magic going on, which takes care of sandboxing,
      logging and some other nice stuff, that you get for free.

      Except that a few other variables like ``self.console`` are available,
      you normally won't notice anything.

Obviously, we need to add some hosts to this node. In the following example we
link it to localhost.

::

    from deployer.host import LocalHost

    class SayHelloOnLocalHost(SayHello):
        class Hosts:
            host = LocalHost

Now we have two quick ways of running this code. The first one is programmatically:

::

    from deployer.node import Env

    env = Env(AptGetOnLocalHost())

    env.update()
    env.install()

The other way is to create an interactive shell around this node. Typically,
you do it as follows:

::

    if __name__ == '__main__':
        from deployer.client import start
        start(AptGetOnLocalHost)

If you save it as ``deployment.py`` and call like below you'll get a nice shell
from which you can run the `update` and `install` commands.

::

    python deployment.py run


Adding SSH Hosts
----------------

Instead of using `LocalHost`, you can link an SSH host to the node.

::

    from deployer.host import SSHHost

    class MyRemoteHost(SSHHost):
        slug = 'my-host'
        address = '192.168.0.200'
        username = 'john'
        password = '...'

    class MyNode(SimpleNode):
        class Hosts:
            host = MyRemoteHost


Inheritance
-----------

A node is meant to be reusable. It is encouraged to inherit from such a node
class and overwrite properties or class members.

contrib.nodes
*************

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


.. toctree::
   :maxdepth: 3

   pages/console
   pages/exceptions
   pages/host_container
   pages/inspection
   pages/node
   pages/pseudo_terminal
   pages/query
   pages/utils

   pages/about
