The Console object
==================

An instance of the console object is exposed as a property of a Node. It can be
used to query the user for information. e.g.

::

    class MyNode(Node):
        def do_something(self):
            if self.console.confirm('Should we really do this?', default=True):
                # Do it...
                pass

The cool thing is that when the script runs in a shell that was started with an
interactive=False parameter, the default options will be chosen automatically.
It also takes care of the pty object underneat.

Class attributes
----------------

.. automodule:: deployer.console
    :members:

