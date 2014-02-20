#!/usr/bin/env python
"""
Start this file as "./simple_deployment run"

Then you can for instance do this:
    > cd examples
    > say_hello
    > --connect
    > exit
"""

from deployer.host import LocalHost
from deployer.node import Node


class example_settings(Node):
    # Run everything on the local machine
    class Hosts:
        host = { LocalHost }

    # A nested node with some examples.
    class examples(Node):
        def say_hello(self):
            self.hosts.run('echo hello world')

        def directory_listing_in_superuser_home(self):
            self.hosts.sudo('ls ~')

        def return_hello_world(self):
            return 'Hello world'

        def raise_exception(self):
            raise Exception('Custom exception')


if __name__ == '__main__':
    # Start an interactive shell.
    from deployer.client import start
    start(root_service=example_settings)
