Getting started
===============

In this short tutorial, we'll demonstrate how to create a simple interactive
shell around one simple deployment command that just prints 'Hello World'. We
suppose you have already an understanding of the Python language and Python
packages.

Hello world
-----------

Install requirements
********************

Install the following package.

::

    pip install deployer

This will probably also install dependencies like ``paramiko``, ``twisted`` and
``pexpect``.


Creating nodes
**************

Now we will create a :class:`deployer.node.Node` to contains the 'Hello world' action.
Such a ``Node`` class is the start for any deployment component. Paste the
following in an empty Python file:

::

    from deployer.node import Node

    class SayHello(Node):
        def hello(self):
            self.hosts.run('echo hello world')

When `SayHello.hello` is called in the example above, it will run the echo
command on all the hosts that are known to this Node.

Linking the node to actual hosts
********************************

Now we need to define on which hosts this node should run. Let's use Python
class inheritance for this. Append the following to your Python file:

::

    from deployer.host import LocalHost

    class SayHelloOnLocalHost(SayHello):
        class Hosts:
            host = LocalHost


Starting an interactive shell
*****************************

One way of execting this code, is by wrapping it in an interactive shell.
This is the last thing to do: add the following to the bottom of your Python
file, and save it as ``my_deployment.py``.

::

    if __name__ == '__main__':
        from deployer.client import start
        start(SayHelloOnLocalHost)

Call it like below, and you'll get a nice interactive shell with tab-completion
from where you can run the ``hello`` command.

::

    python deployment.py run


Remote SSH Hosts
****************

So, in the example we have shown how to run 'Hello world' on your local
machine. That's fine, but probably we want to execute this on a remote machine
that's connected through SSH. That's possible by creating an ``SSHHost`` class
instead of using ``LocalHost``. Make sure to change the credentials to your own.

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

Done
****

As a final example, we show how we created two instances of ``SayHello``. One
mapped to your local machine, and one mapped to a remote SSH Host. These two
nodes are now wrapped in a parent node, that groups both.


::

    #!/usr/bin/env python

    # Imports
    from deployer.client import start
    from deployer.host import SSHHost, LocalHost
    from deployer.node import Node

    # Host definitions
    class MyRemoteHost(SSHHost):
        slug = 'my-host'
        address = '192.168.0.200'
        username = 'john'
        password = '...'

    # The deployment nodes

    class SayHello(Node):
        def hello(self):
            self.hosts.run('echo hello world')

    class RootNode(Node):
        class local_hello(SayHello):
            class Hosts:
                host = LocalHost

        class remote_hello(SayHello):
            class Hosts:
                host = MyRemoteHost

    if __name__ == '__main__':
        start(RootNode)


Where to go now?
----------------

What you learned here is a basic example of how to use the deployment
framework. However, there are much more advanced concepts possible.  A quick
listing of items to learn are the following. (In logical order of learning.)

 - :ref:`Architecture of role and nodes <architecture-of-roles-and-nodes>`
 - :ref:`Inheritance (and double underscore expansion) <node-inheritance>`
 - :ref:`Query expressions <query-expressions>`
 - :ref:`Introspection <inspection>`
