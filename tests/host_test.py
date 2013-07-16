from deployer.host import LocalHost, HostContext
from deployer.host_container import HostsContainer, HostContainer
from deployer.loggers import LoggerInterface
from deployer.pseudo_terminal import Pty, DummyPty
from deployer.utils import IfConfig

from our_hosts import LocalHost, LocalHost1, LocalHost2, LocalHost3, LocalHost4, LocalHost5

import os
import unittest
import tempfile


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

    def test_opening_files(self):
        test_filename = '/tmp/python-deploy-framework-unittest-testfile-1'
        content = 'my-test-content'

        # Writing of file
        host = LocalHost1.get_instance()
        with host.open(test_filename, mode='w') as f:
            f.write(content)

        with open(test_filename, 'r') as f:
            self.assertEqual(f.read(), content)

        # Reading of file.
        with host.open(test_filename, mode='r') as f:
            self.assertEqual(f.read(), content)

        os.remove(test_filename)

    def test_put_file(self):
        host = LocalHost1.get_instance()

        # Create temp file
        fd, name1 = tempfile.mkstemp()
        with os.fdopen(fd, 'w') as f:
            f.write('my-data')

        # Put operations
        _, name2 = tempfile.mkstemp()
        host.put_file(name1, name2)

        with open(name1) as f:
            with open(name2) as f2:
                self.assertEqual(f.read(), f2.read())

        # Get operation
        _, name3 = tempfile.mkstemp()
        host.get_file(name1, name3)

        with open(name1) as f:
            with open(name3) as f2:
                self.assertEqual(f.read(), f2.read())

        # clean up
        os.remove(name1)
        os.remove(name2)
        os.remove(name3)

    def test_ifconfig(self):
        # ifconfig should return an IfConfig instance.
        host = LocalHost1.get_instance()
        self.assertIsInstance(host.ifconfig(), IfConfig)

if __name__ == '__main__':
    unittest.main()
