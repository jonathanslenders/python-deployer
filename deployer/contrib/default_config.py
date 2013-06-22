from deployer.contrib.loggers.on_host import OnHostLogger
from deployer.contrib.nodes.connect import Connect
from deployer.contrib.unittest.nodes import UnitTest
from deployer.host import SSHHost, LocalHost
from deployer.node import Node, map_roles

from inspect import isclass


class localhost(LocalHost):
    slug = 'localhost'

'''
class my_remote_host(SSHHost):
    slug = 'my-remote-host'
    address = '192.168.0.100'
    username = 'username'
    password = 'password'
'''

class example_settings(Node):
    class Hosts:
        host = [ localhost ]

    class examples(Node):
        def say_hello(self):
            self.hosts.run('echo hello world')

        def directory_listing_in_superuser_home(self):
            self.hosts.sudo('ls ~')

        def return_hello_world(self):
            return 'Hello world'

    connect = map_roles('host')(Connect.Array)
