import random
import unittest

from deployer.query import Q
from deployer.service import Service
from deployer.host import LocalHost
from deployer.pty import Pty, DummyPty
from deployer.loggers import LoggerInterface

"""

This is a start at writing unit tests for everything.

"""

class SimpleServiceTest(unittest.TestCase):
    def test_simple_service(self):
        class MyService(Service):
            class Hosts:
                host = LocalHost

            def my_action(self):
                return 'result'

        s = MyService()
        result = s.my_action().run(DummyPty(), LoggerInterface())
        self.assertEqual(result, ['result']) # XXX This shouldn't be an array -- I think

    def test_simple_service_with_params(self):
        class MyService(Service):
            class Hosts:
                host = LocalHost

            def my_action(self, param1, *a, **kw):
                return (param1, a, kw)

        s = MyService()
        result = s.my_action('param1', 1, 2, k=3, v=4).run(DummyPty(), LoggerInterface())
        self.assertEqual(result, [ ('param1', (1, 2), { 'k': 3, 'v': 4 }) ] ) # XXX This shouldn't be an array -- I think

    def test_echo(self):
        class MyService(Service):
            class Hosts:
                host = LocalHost

            def my_action(self):
                return self.hosts.run('/bin/echo echo', interactive=False)

        s = MyService()
        result = s.my_action().run(DummyPty(), LoggerInterface())
        self.assertEqual(result, [['echo\r\n']]) # XXX This should be a single array -- I think


class Q_ObjectTest(unittest.TestCase):
    def test_q_expressions(self):
        # String constant
        q = Q('string')
        self.assertEqual(q._query(None), 'string')

        # Simple operator overloads (Both Q objects)
        q = Q('a') + Q('b')
        self.assertEqual(q._query(None), 'ab')

        q = Q(1) + Q(2)
        self.assertEqual(q._query(None), 3)

        q = Q(2) - Q(1)
        self.assertEqual(q._query(None), 1)

        q = Q(3) * Q(4)
        self.assertEqual(q._query(None), 12)

        q = Q(12) / Q(4)
        self.assertEqual(q._query(None), 3)

        # Simple operator overloads (Q object on the left.)
        q = Q('a') + 'b'
        self.assertEqual(q._query(None), 'ab')

        q = Q(1) + 2
        self.assertEqual(q._query(None), 3)

        q = Q(2) - 1
        self.assertEqual(q._query(None), 1)

        q = Q(3) * 4
        self.assertEqual(q._query(None), 12)

        q = Q(12) / 4
        self.assertEqual(q._query(None), 3)

        # Simple operator overloads (Q object on the right.)
        q = 'a' + Q('b')
        self.assertEqual(q._query(None), 'ab')

        q = 1 + Q(2)
        self.assertEqual(q._query(None), 3)

        q = 2 - Q(1)
        self.assertEqual(q._query(None), 1)

        q = 3 * Q(4)
        self.assertEqual(q._query(None), 12)

        q = 12 / Q(4)
        self.assertEqual(q._query(None), 3)

        # String interpolation
        q = Q('before %s after') % 'value'
        self.assertEqual(q._query(None), 'before value after')

if __name__ == '__main__':
    unittest.main()
