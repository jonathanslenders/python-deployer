import unittest

from deployer.host import LocalHost, HostContext
from deployer.host_container import HostsContainer, HostContainer
from deployer.pseudo_terminal import Pty, DummyPty
from deployer.loggers import LoggerInterface

from our_hosts import LocalHost, LocalHost1, LocalHost2, LocalHost3, LocalHost4, LocalHost5


class HostsContainerTest(unittest.TestCase):
    def get_definition(self):
        class Hosts:
            role1 = LocalHost1, LocalHost2
            role2 = LocalHost3, LocalHost4, LocalHost5
            role3 = LocalHost1

        return HostsContainer.from_definition(Hosts, pty=DummyPty())

    def test_from_invalid_definition(self):
        class Hosts:
            invalid = 4
            class invalid2(object):
                pass

        self.assertRaises(TypeError, HostsContainer.from_definition, Hosts)


    def test_host_container(self):
        hosts_container = self.get_definition()

        # (fuzzy) __repr__
        self.assertIn('role1', repr(hosts_container))
        self.assertIn('role2', repr(hosts_container))
        self.assertIn('role3', repr(hosts_container))

        # __eq__
        self.assertEqual(hosts_container, self.get_definition())

        # __len__
        self.assertEqual(len(hosts_container), 5)

        # __nonzero__
        self.assertEqual(bool(hosts_container), True)

        # roles
        self.assertEqual(hosts_container.roles, ['role1', 'role2', 'role3'])

     #   # __contains__
     #   print hosts_container._all
     #   print LocalHost3 in hosts_container._all
     #   print LocalHost3 == LocalHost3
     #   self.assertIn(LocalHost3, hosts_container)

        # get_from_slug
        self.assertEqual(hosts_container.get_from_slug('localhost2')._host, LocalHost2)

        # contains_host_with_slug
        self.assertEqual(hosts_container.contains_host_with_slug('localhost2'), True)
        self.assertEqual(hosts_container.contains_host_with_slug('unknown-host'), False)

        # Filter
        self.assertEqual(len(hosts_container.filter('role1')), 2)
        self.assertEqual(len(hosts_container.filter('role2')), 3)
        self.assertEqual(len(hosts_container.filter('role3')), 1)

        # Filter-*
        self.assertEqual(len(hosts_container.filter('*')), 5)

        class MyHosts1:
            role1 = LocalHost1, LocalHost2
        class MyHosts2:
            role2 = LocalHost3, LocalHost4, LocalHost5

        self.assertEqual(hosts_container.filter('role1'), HostsContainer.from_definition(MyHosts1))
        self.assertEqual(hosts_container.filter('role2'), HostsContainer.from_definition(MyHosts2))
        self.assertNotEqual(hosts_container.filter('role1'), HostsContainer.from_definition(MyHosts2))
        self.assertNotEqual(hosts_container.filter('role2'), HostsContainer.from_definition(MyHosts1))

        # Filter on two roles.

        class MyHosts1_and_2:
            role1 = LocalHost1, LocalHost2
            role2 = LocalHost3, LocalHost4, LocalHost5

        self.assertEqual(hosts_container.filter('role1', 'role2'), HostsContainer.from_definition(MyHosts1_and_2))
        self.assertNotEqual(hosts_container.filter('role1', 'role2'), HostsContainer.from_definition(MyHosts1))

        # get
        self.assertRaises(AttributeError, hosts_container.get, 'role1') # Role with multiple hosts
        self.assertRaises(AttributeError, hosts_container.get, 'unknown-role')
        self.assertEqual(hosts_container.get('role3')._host, LocalHost1)

        # __iter__
        count = 0
        for i in hosts_container:
            self.assertIsInstance(i, HostContainer)
            count += 1
        self.assertEqual(count, 5)

    def test_hostcontainer_run(self):
        hosts_container = self.get_definition()

        # Simple run
        result = hosts_container.run('echo test', interactive=False)
        self.assertEqual(len(result), 5)
        self.assertEqual(len(set(result)), 1) # All results should be equal
        self.assertEqual(result[0].strip(), 'test')

        # Env
        with hosts_container.env('CUSTOM_VAR', 'my-value'):
            result = hosts_container.run('echo $CUSTOM_VAR', interactive=False)
            self.assertEqual(result[0].strip(), 'my-value')

        # Env/filter combination
        with hosts_container.filter('role2').env('CUSTOM_VAR', 'my-value'):
            result = hosts_container.run('echo var=$CUSTOM_VAR', interactive=False)
            self.assertEqual(all('var=' in i for i in result), True)
            self.assertEqual(len(filter((lambda i: 'my-value' in i), result)), 3)

    def test_hostcontainer_commands(self):
        # Exists (the current directory should exist)
        hosts_container = self.get_definition()
        self.assertEqual(hosts_container.exists('.', use_sudo=False), [True, True, True, True, True])
        self.assertEqual(hosts_container[0].exists('.', use_sudo=False), True)

        # Has command
        self.assertEqual(hosts_container.has_command('ls'), [True, True, True, True, True])
        self.assertEqual(hosts_container[0].has_command('ls'), True)

    def test_hostcontainer_cd(self):
        hosts_container = self.get_definition()

        with hosts_container.cd('/'):
            result = hosts_container.run('pwd', interactive=False)
            self.assertEqual(len(result), 5)
            self.assertEqual(result[0].strip(), '/')

    def test_hostcontainer_prefix(self):
        hosts_container = self.get_definition()

        with hosts_container.prefix('echo hello'):
            result = hosts_container.run('echo world', interactive=False)
            self.assertIn('hello', result[0])
            self.assertIn('world', result[0])

    def test_expand_path(self):
        hosts_container = self.get_definition()

        self.assertIsInstance(hosts_container.expand_path('.'), list)
        self.assertIsInstance(hosts_container[0].expand_path('.'), basestring)
