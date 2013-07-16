from deployer.inspection.inspector import Inspector, PathType

__doc__ = \
"""
The inspection module contains a set of utilities for introspection of the
deployment tree. This can be either from inside an action, or externally to
reflect on a given tree.

Suppose that we already have the following node instantiated:

::

    from deployer.node import Node

    class Setup(Node):
        def say_hello(self):
            self.hosts.run('echo "Hello world"')

    setup = Setup()

Now we can ask for the list of actions that this node has:

::

    from deployer.inspection import Inspector

    insp = Inspector(setup)
    print insp.get_actions()
    print insp.get_childnodes()

"""


