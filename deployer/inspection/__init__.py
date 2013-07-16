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

Some usecases:

- Suppose that you have a huge deployment tree, covering dozens of projects,
  each having both a staging and production set-up, and all of them are doing a
  git checkout. Now you want to list all the current checkouts of all the
  repositories on all your machines. This is easy by traversing the nodes, filtering
  on the type `gitnode` and calling `git show` in there.
- Suppose you have an `nginx` node, which generates the configuration according
  to the childnodes in there. One childnode could for instance define a
  back-end, another one could define the location of static files, etc... By
  using this inspection module, you cat find the childnodes that contain a
  configuration section and combine these.
- Internally, the whole interactive shell is also using quite a lot of reflection.

"""
