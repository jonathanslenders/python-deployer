from deployer.pseudo_terminal import DummyPty
from deployer.utils import IfConfig
from deployer.host.base import Stat

from our_hosts import LocalHost1

import os
import unittest
import tempfile


class HostTest(unittest.TestCase):
    def test_simple_echo_command(self):
        host = LocalHost1()
        self.assertEqual(host.run('echo test', interactive=False).strip(), 'test')

    def test_host_context(self):
        host = LocalHost1()
        context = host.host_context

        # Test __repr__
        self.assertIn('HostContext(', repr(context))

        # Test env.
        with context.env('CUSTOM_VAR', 'my-value'):
            self.assertEqual(host.run('echo $CUSTOM_VAR', interactive=False).strip(), 'my-value')
        self.assertEqual(host.run('echo $CUSTOM_VAR', interactive=False).strip(), '')

        # Test prefix
        with context.prefix('echo prefix'):
            result = host.run('echo command', interactive=False)
            self.assertIn('prefix', result)
            self.assertIn('command', result)

        # Test 'cd /'
        with context.cd('/'):
            self.assertEqual(host.run('pwd', interactive=False).strip(), '/')

        # Test env nesting.
        with context.env('VAR1', 'var1'):
            with context.env('VAR2', 'var2'):
                self.assertEqual(host.run('echo $VAR1-$VAR2', interactive=False).strip(), 'var1-var2')

        # Test escaping.
        with context.env('VAR1', 'var1'):
            with context.env('VAR2', '$VAR1', escape=False):
                self.assertEqual(host.run('echo $VAR2', interactive=False).strip(), 'var1')

            with context.env('VAR2', '$VAR1'): # escape=True by default
                self.assertEqual(host.run('echo $VAR2', interactive=False).strip(), '$VAR1')

    def test_repr(self):
        host = LocalHost1()
        self.assertIn('Host(', repr(host))

    def test_interactive(self):
        # XXX: Not entirely sure whether this test is reliable.
        #      -> the select-loop will stop as soon as no input is available on any end.
        host = LocalHost1()

        result = host.run('echo test').strip()
        self.assertEqual(result, 'test')

    def test_input(self):
        pty = DummyPty('my-input\n')
        host = LocalHost1(pty=pty)

        result = host.run('read varname; echo $varname')
        self.assertEqual(result, 'my-input\r\nmy-input\r\n')

    def test_opening_files(self):
        test_filename = '/tmp/python-deploy-framework-unittest-testfile-1'
        content = 'my-test-content'

        # Writing of file
        host = LocalHost1()
        with host.open(test_filename, mode='w') as f:
            f.write(content)

        with open(test_filename, 'r') as f:
            self.assertEqual(f.read(), content)

        # Reading of file.
        with host.open(test_filename, mode='r') as f:
            self.assertEqual(f.read(), content)

        os.remove(test_filename)

    def test_put_file(self):
        host = LocalHost1()

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

    def test_stat(self):
        """ Test the stat method. """
        host = LocalHost1()

        # Create temp file
        fd, name = tempfile.mkstemp()

        # Call stat on temp file.
        s = host.stat(name)
        self.assertIsInstance(s, Stat)
        self.assertEqual(s.st_size, 0)
        self.assertEqual(s.is_file, True)
        self.assertEqual(s.is_dir, False)
        self.assertIsInstance(s.st_uid, int)
        self.assertIsInstance(s.st_gid, int)
        os.remove(name)

        # Call stat on directory
        s = host.stat('/tmp')
        self.assertEqual(s.is_file, False)
        self.assertEqual(s.is_dir, True)

    def test_ifconfig(self):
        # ifconfig should return an IfConfig instance.
        host = LocalHost1()
        self.assertIsInstance(host.ifconfig(), IfConfig)

    def test_listdir(self):
        host = LocalHost1()
        with host.host_context.cd('/'):
            self.assertIsInstance(host.listdir(), list)

    def test_listdir_stat(self):
        host = LocalHost1()

        result = host.listdir_stat('/tmp')
        self.assertIsInstance(result, list)
        for r in result:
            self.assertIsInstance(r, Stat)

if __name__ == '__main__':
    unittest.main()
