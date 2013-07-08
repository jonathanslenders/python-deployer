Getting started
===============

Install the framework as follows:

::

    pip install deployer


Hello world
-----------

Creating nodes
**************

As a quick example, we create a simple node, which does nothing, except
printing 'hello world', by executing an `echo` command.

::

    from deployer.node import SimpleNode

    class SayHello(SimpleNode):
        def hello(self):
            self.host.run('echo hello world')

When `SayHello.hello` is called in the example above, it will run the echo
command on all the hosts that are known in this Node.

.. note:: It is interesting to know that ``self`` is actually not a ``Node`` instance,
      but an ``Env`` object which will proxy this actual Node class. This is
      because there is some metaclass magic going on, which takes care of sandboxing,
      logging and some other nice stuff, that you get for free.

      Except that a few other variables like ``self.console`` are available,
      you normally won't notice anything.

Now we need to define on which hosts this node should run. Let's use Python
class inheritance for this.

::

    from deployer.host import LocalHost

    class SayHelloOnLocalHost(SayHello):
        class Hosts:
            host = LocalHost

Executing nodes
***************

Now we have two quick ways of running this code. The first one is programmatically:

::

    from deployer.node import Env

    env = Env(SayHelloOnLocalHost())
    env.hello()

The other way is to create an interactive shell around this node. Typically,
you do it as follows:

::

    if __name__ == '__main__':
        from deployer.client import start
        start(SayHelloOnLocalHost)

If you save it as ``deployment.py`` and call like below you'll get a nice shell
from which you can run the `hello` commands.

::

    python deployment.py run

.. note:: Don't forget that the interactive shell has tab-completion. For most
          people this will be the fastest, most user-friendly way of
          interacting with the nodes.


Remote SSH Hosts
****************

Instead of using `LocalHost`, you can link an SSH host to the node.

::

    from deployer.host import SSHHost

    class MyRemoteHost(SSHHost):
        slug = 'my-host'
        address = '192.168.0.200'
        username = 'john'
        password = '...'

    class RemoteHello(SayHello):
        class Hosts:
            host = MyRemoteHost
