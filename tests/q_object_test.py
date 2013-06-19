import unittest

from deployer.query import Q
from deployer.node import Node, SimpleNode, Env

from our_hosts import LocalHost, LocalHost1, LocalHost2, LocalHost3, LocalHost4, LocalHost5


class Q_ObjectTest(unittest.TestCase):
    def test_q_expressions(self):
        # Literals
        q = Q('string')
        self.assertEqual(q._query(None), 'string')

        q = Q(55)
        self.assertEqual(q._query(None), 55)

        q = Q(True)
        self.assertEqual(q._query(None), True)

        q = Q(False)
        self.assertEqual(q._query(None), False)

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

        # And/or/not
        q = Q(True) & Q(True)
        self.assertEqual(q._query(None), True)

        q = Q(True) & Q(False)
        self.assertEqual(q._query(None), False)

        q = Q(True) | Q(False)
        self.assertEqual(q._query(None), True)

        q = Q(False) | Q(False)
        self.assertEqual(q._query(None), False)

        q = ~ Q(False)
        self.assertEqual(q._query(None), True)

        q = ~ Q(True)
        self.assertEqual(q._query(None), False)

        # Combinations
        q = Q(False) | ~ Q(False)
        self.assertEqual(q._query(None), True)

    def test_q_attribute_selection(self):
        class Obj(object):
            value = 'value'

            def action(self):
                return 'action-result'

            def __getitem__(self, item):
                return 'item %s' % item

            def true(self): return True
            def false(self): return False

        obj = Obj()
        obj.nested_obj = obj

        # Combinations of attribute lookups, __getitem__ and calling.
        q = Q.value
        self.assertEqual(q._query(obj), 'value')

        q = Q['attr']
        self.assertEqual(q._query(obj), 'item attr')

        q = Q.action()
        self.assertEqual(q._query(obj), 'action-result')

        q = Q.nested_obj.action()
        self.assertEqual(q._query(obj), 'action-result')

        q = Q.nested_obj.action()
        self.assertEqual(q._query(obj), 'action-result')

        q = Q.nested_obj.nested_obj['attr']
        self.assertEqual(q._query(obj), 'item attr')

        # Add some operators
        q = Q.nested_obj.nested_obj.value + '-' + Q.value
        self.assertEqual(q._query(obj), 'value-value')

        q = ~ Q.true()
        self.assertEqual(q._query(obj), False)

        q = Q.true() & Q.nested_obj.true()
        self.assertEqual(q._query(obj), True)

        q = Q.true() | Q.nested_obj.false()
        self.assertEqual(q._query(obj), True)

    def test_q_navigation(self):
        class MyNode(Node):
            class Hosts:
                host = LocalHost

            attr = 'value'
            query = Q.attr
            query2 = Q.attr + Q.attr

            def my_action(self):
                return self.query

        s = MyNode()
        env = Env(s)
        self.assertEqual(env.my_action(), 'value')
        self.assertEqual(env.query2, 'valuevalue')

