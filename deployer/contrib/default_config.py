from deployer.contrib.loggers.on_host import OnHostLogger
from deployer.contrib.services.connect import Connect
from deployer.contrib.services.monitoring import Monitor
from deployer.contrib.unittest.services import UnitTest
from deployer.host import SSHHost, Host, LocalHost
from deployer.service import Service
from deployer.service_groups import Other

from inspect import isclass

#
# Host definitions
#

class localhost(LocalHost):
    slug = 'localhost'

'''
class my_remote_host(SSHHost):
    slug = 'my-remote-host'
    address = '192.168.0.100'
    username = 'username'
    password = 'password'
'''

#
# Service definitions
#

class Examples(Service):
    """
    Example service that
    """
    class Meta:
        group = None

    def say_hello(self):
        self.hosts.run('echo hello world')

    def directory_listing_in_superuser_home(self):
        self.hosts.sudo('ls ~')

#
# Settings
#


class example_settings(Service):
    class Meta:
        # Default group name. (Can be overriden for every nested service.)
        group = Other

        # Global loggers
        extra_loggers = []

        # # Use the following instead for logging of all events
        # # in ~/.deployer/history on every host.
        # extra_loggers = [ OnHostLogger(getpass.getuser()) ]

    class Hosts:
        # Collect all hosts that are defined above in the root service.
        host = [ v for v in globals().values() if isclass(v) and issubclass(v, SSHHost) and v.slug ] + [ localhost ]

    #
    # Services mapped to their hosts
    #

    class examples(Examples):
        class Hosts:
            host = localhost

    connect = Connect
    monitor_host = Monitor

    # For unit-testing the deployer
    unit_test = UnitTest
