import os
import tempfile
import unittest

from deployer.host_container import HostsContainer, HostContainer
from deployer.pseudo_terminal import DummyPty

from our_hosts import LocalHost1, LocalHost2, LocalHost3, LocalHost4, LocalHost5


class HostsContainerTest(unittest.TestCase):
    def get_definition(self):
        class Hosts:
            role1 = { LocalHost1, LocalHost2 }
            role2 = { LocalHost3, LocalHost4, LocalHost5 }
            role3 = { LocalHost1 }

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

        # __eq__ of get_hosts_as_dict
        # (__eq__ of HostsContainer itself is not supported anymore.)
        self.assertEqual(hosts_container.get_hosts_as_dict(),
                    self.get_definition().get_hosts_as_dict())

        # __len__ (One host appeared in two roles, both will be counted, so 6)
        self.assertEqual(len(hosts_container), 6)

        # __nonzero__
        self.assertEqual(bool(hosts_container), True)

        # roles
        self.assertEqual(hosts_container.roles, ['role1', 'role2', 'role3'])

     #   # __contains__
     #   self.assertIn(LocalHost3, hosts_container)

        # Filter
        self.assertEqual(len(hosts_container.filter('role1')), 2)
        self.assertEqual(len(hosts_container.filter('role2')), 3)
        self.assertEqual(len(hosts_container.filter('role3')), 1)

        # Non string filter should raise exception.
        self.assertRaises(TypeError, HostsContainer.filter, 123)

        class MyHosts1:
            role1 = { LocalHost1, LocalHost2 }
        class MyHosts2:
            role2 = { LocalHost3, LocalHost4, LocalHost5 }

        self.assertIsInstance(hosts_container.filter('role1'), HostsContainer)
        self.assertIsInstance(hosts_container.filter('role2'), HostsContainer)
        self.assertEqual(hosts_container.filter('role1').get_hosts(), set(MyHosts1.role1))
        self.assertEqual(hosts_container.filter('role2').get_hosts(), set(MyHosts2.role2))

        self.assertEqual(hosts_container.filter('role1').get_hosts_as_dict(),
                HostsContainer.from_definition(MyHosts1).get_hosts_as_dict())
        self.assertEqual(hosts_container.filter('role2').get_hosts_as_dict(),
                HostsContainer.from_definition(MyHosts2).get_hosts_as_dict())
        self.assertNotEqual(hosts_container.filter('role1').get_hosts_as_dict(),
                HostsContainer.from_definition(MyHosts2).get_hosts_as_dict())
        self.assertNotEqual(hosts_container.filter('role2').get_hosts_as_dict(),
                HostsContainer.from_definition(MyHosts1).get_hosts_as_dict())

        # Filter on two roles.

        class MyHosts1_and_2:
            role1 = { LocalHost1, LocalHost2 }
            role2 = { LocalHost3, LocalHost4, LocalHost5 }

        self.assertEqual(hosts_container.filter('role1', 'role2').get_hosts_as_dict(),
                    HostsContainer.from_definition(MyHosts1_and_2).get_hosts_as_dict())

        # __iter__ (will yield 6 items: when several roles contain the same
        # host, it are different instances.)
        count = 0
        for i in hosts_container:
            self.assertIsInstance(i, HostContainer)
            count += 1
        self.assertEqual(count, 6)

    def test_hostcontainer_run(self):
        hosts_container = self.get_definition()

        # Simple run
        result = hosts_container.run('echo test', interactive=False)
        self.assertEqual(len(result), 6)
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
        self.assertEqual(hosts_container.exists('.', use_sudo=False), [True, True, True, True, True, True])
        self.assertEqual(hosts_container[0].exists('.', use_sudo=False), True)

        # Has command
        self.assertEqual(hosts_container.has_command('ls'), [True, True, True, True, True, True])
        self.assertEqual(hosts_container[0].has_command('ls'), True)

        # (unknown command
        unknown_command = 'this_is_an_unknown_command'
        self.assertEqual(hosts_container.has_command(unknown_command),
                        [False, False, False, False, False, False])
        self.assertEqual(hosts_container[0].has_command(unknown_command), False)

    def test_hostcontainer_cd(self):
        hosts_container = self.get_definition()

        with hosts_container.cd('/'):
            result = hosts_container.run('pwd', interactive=False)
            self.assertEqual(len(result), 6)
            self.assertEqual(result[0].strip(), '/')
            self.assertEqual(hosts_container[0].getcwd(), '/')
            self.assertEqual(hosts_container.getcwd(), ['/'] * 6)

    def test_hostcontainer_cd2(self):
        # Test exists in cd.
        # (Exists should be aware of the cd-context.)
        hosts_container = self.get_definition()

        with hosts_container.cd('/'):
            self.assertEqual(hosts_container.exists('.', use_sudo=False), [True, True, True, True, True, True])
        with hosts_container.cd('/some-unknown-directory'):
            self.assertEqual(hosts_container.exists('.', use_sudo=False), [False, False, False, False, False, False])
        with hosts_container.cd('/'):
            self.assertEqual(hosts_container[0].exists('.', use_sudo=False), True)
        with hosts_container.cd('/some-unknown-directory'):
            self.assertEqual(hosts_container[0].exists('.', use_sudo=False), False)

    def test_hostcontainer_prefix(self):
        hosts_container = self.get_definition()

        with hosts_container.prefix('echo hello'):
            result = hosts_container.run('echo world', interactive=False)
            self.assertIn('hello', result[0])
            self.assertIn('world', result[0])

    def test_expand_path(self):
        hosts_container = self.get_definition()

        self.assertIsInstance(hosts_container.expand_path('.'), list)
        self.assertIsInstance(hosts_container.filter('role3')[0].expand_path('.'), basestring)

    def test_file_open(self):
        hosts_container = self.get_definition()

        # Open function should not exist in HostsContainer, only in HostContainer
        self.assertRaises(AttributeError, lambda: hosts_container.getattr('open'))

        # Call open function.
        _, name = tempfile.mkstemp()
        container = hosts_container.filter('role3')[0]
        with container.open(name, 'w') as f:
            f.write('my-content')

        # Verify content
        with open(name, 'r') as f:
            self.assertEqual(f.read(), 'my-content')

        os.remove(name)

    def test_put_and_get_file(self):
        hosts_container = self.get_definition()
        host_container = hosts_container.filter('role3')[0]

        # putfile/getfile functions should not exist in HostsContainer, only in HostContainer
        self.assertRaises(AttributeError, lambda: hosts_container.getattr('put_file'))
        self.assertRaises(AttributeError, lambda: hosts_container.getattr('get_file'))

        # Create temp file
        fd, name1 = tempfile.mkstemp()
        with os.fdopen(fd, 'w') as f:
            f.write('my-data')

        # Put operations
        _, name2 = tempfile.mkstemp()
        host_container.put_file(name1, name2)

        with open(name1) as f:
            with open(name2) as f2:
                self.assertEqual(f.read(), f2.read())

        # Get operation
        _, name3 = tempfile.mkstemp()
        host_container.get_file(name1, name3)

        with open(name1) as f:
            with open(name3) as f2:
                self.assertEqual(f.read(), f2.read())

        # clean up
        os.remove(name1)
        os.remove(name2)
        os.remove(name3)


