import unittest

from deployer.host import LocalHost, HostContext
from deployer.host_container import HostsContainer, HostContainer
from deployer.pseudo_terminal import Pty, DummyPty
from deployer.loggers import LoggerInterface

from tests.our_hosts import LocalHost, LocalHost1, LocalHost2, LocalHost3, LocalHost4, LocalHost5



class HostTest(unittest.TestCase):
    def test_simple_echo_command(self):
        host = LocalHost1.get_instance()
        pty = DummyPty()
        self.assertEqual(host.run(pty, 'echo test', interactive=False).strip(), 'test')

    def test_host_context(self):
        host = LocalHost1.get_instance()
        context = HostContext()
        pty = DummyPty()

        # Test env.
        with context.env('CUSTOM_VAR', 'my-value'):
            self.assertEqual(host.run(pty, 'echo $CUSTOM_VAR', interactive=False, context=context).strip(), 'my-value')
        self.assertEqual(host.run(pty, 'echo $CUSTOM_VAR', interactive=False, context=context).strip(), '')

        # Test prefix
        with context.prefix('echo prefix'):
            result = host.run(pty, 'echo command', interactive=False, context=context)
            self.assertIn('prefix', result)
            self.assertIn('command', result)

        # Test 'cd /'
        with context.cd('/'):
            self.assertEqual(host.run(pty, 'pwd', interactive=False, context=context).strip(), '/')

        # Test env nesting.
        with context.env('VAR1', 'var1'):
            with context.env('VAR2', 'var2'):
                self.assertEqual(host.run(pty, 'echo $VAR1-$VAR2', interactive=False, context=context).strip(), 'var1-var2')

        # Test escaping.
        with context.env('VAR1', 'var1'):
            with context.env('VAR2', '$VAR1', escape=False):
                self.assertEqual(host.run(pty, 'echo $VAR2', interactive=False, context=context).strip(), 'var1')

            with context.env('VAR2', '$VAR1'): # escape=True by default
                self.assertEqual(host.run(pty, 'echo $VAR2', interactive=False, context=context).strip(), '$VAR1')

    def test_interactive(self):
        # XXX: Not entirely sure whether this test is reliable.
        #      -> the select-loop will stop as soon as no input is available on any end.
        host = LocalHost1.get_instance()
        pty = DummyPty()

        result = host.run(pty, 'echo test').strip()
        self.assertEqual(result, 'test')

    def test_input(self):
        host = LocalHost1.get_instance()
        pty = DummyPty('my-input\n')

        result = host.run(pty, 'read varname; echo $varname')
        self.assertEqual(result, 'my-input\r\nmy-input\r\n')


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

if __name__ == '__main__':
    unittest.main()
