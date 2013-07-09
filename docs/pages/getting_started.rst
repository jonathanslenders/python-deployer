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

Now we need to define on which hosts this node should run. Let's use Python
class inheritance for this.

::

    from deployer.host import LocalHost

    class SayHelloOnLocalHost(SayHello):
        class Hosts:
            host = LocalHost

Starting an interactive shell
*****************************

Add the following to your Python file, and save it as ``deployment.py``.

::

    if __name__ == '__main__':
        from deployer.client import start
        start(SayHelloOnLocalHost)

If you call it like below, you get a nice interactive shell with tab-completion
from where you can run the ``hello`` command.

::

    python deployment.py run


Remote SSH Hosts
****************

Instead of using ``LocalHost``, you can also run the code on an SSH host.

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

If is even possible to put several instances of the ``SayHello`` node in your
deployment tree, for instance, where one instance is local and the other is
remote.
