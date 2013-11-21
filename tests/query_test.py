import unittest

from deployer.query import Q, Query, QueryResult
from deployer.node import Node, Env
from deployer.exceptions import QueryException, ActionException

from .our_hosts import LocalHost


def get_query_result(query, instance):
    return query._execute_query(instance).result


class ExpressionTest(unittest.TestCase):
    def test_literals(self):
        # Literals
        q = Q('string')
        self.assertEqual(get_query_result(q, None), 'string')

        q = Q(55)
        self.assertEqual(get_query_result(q, None), 55)

        q = Q(True)
        self.assertEqual(get_query_result(q, None), True)

        q = Q(False)
        self.assertEqual(get_query_result(q, None), False)

    def test_operator_overloads(self):
        # Simple operator overloads (Both Q objects)
        q = Q('a') + Q('b')
        self.assertEqual(get_query_result(q, None), 'ab')

        q = Q(1) + Q(2)
        self.assertEqual(get_query_result(q, None), 3)

        q = Q(2) - Q(1)
        self.assertEqual(get_query_result(q, None), 1)

        q = Q(3) * Q(4)
        self.assertEqual(get_query_result(q, None), 12)

        q = Q(12) / Q(4)
        self.assertEqual(get_query_result(q, None), 3)

        # Simple operator overloads (Q object on the left.)
        q = Q('a') + 'b'
        self.assertEqual(get_query_result(q, None), 'ab')

        q = Q(1) + 2
        self.assertEqual(get_query_result(q, None), 3)

        q = Q(2) - 1
        self.assertEqual(get_query_result(q, None), 1)

        q = Q(3) * 4
        self.assertEqual(get_query_result(q, None), 12)

        q = Q(12) / 4
        self.assertEqual(get_query_result(q, None), 3)

        # Simple operator overloads (Q object on the right.)
        q = 'a' + Q('b')
        self.assertEqual(get_query_result(q, None), 'ab')

        q = 1 + Q(2)
        self.assertEqual(get_query_result(q, None), 3)

        q = 2 - Q(1)
        self.assertEqual(get_query_result(q, None), 1)

        q = 3 * Q(4)
        self.assertEqual(get_query_result(q, None), 12)

        q = 12 / Q(4)
        self.assertEqual(get_query_result(q, None), 3)

    def test_string_interpolation(self):
        # String interpolation
        q = Q('before %s after') % 'value'
        self.assertEqual(get_query_result(q, None), 'before value after')

    def test_booleans(self):
        # And/or/not
        q = Q(True) & Q(True)
        self.assertEqual(get_query_result(q, None), True)

        q = Q(True) & Q(False)
        self.assertEqual(get_query_result(q, None), False)

        q = Q(True) | Q(False)
        self.assertEqual(get_query_result(q, None), True)

        q = Q(False) | Q(False)
        self.assertEqual(get_query_result(q, None), False)

        q = ~ Q(False)
        self.assertEqual(get_query_result(q, None), True)

        q = ~ Q(True)
        self.assertEqual(get_query_result(q, None), False)

        # Combinations
        q = Q(False) | ~ Q(False)
        self.assertEqual(get_query_result(q, None), True)

    def test_resolve_types(self):
        q = Q(Q('a'))
        self.assertEqual(get_query_result(q, None), 'a')

        q = Q([Q('%s') % 'a'])
        self.assertEqual(get_query_result(q, None), ['a'])

        q = Q('%s: %s') % ('a', 'b')
        self.assertEqual(get_query_result(q, None), 'a: b')

        q = Q('%s: %s') % (Q('a'), Q('b'))
        self.assertEqual(get_query_result(q, None), 'a: b')

        q = Q(['a', 'b']) + ['c', 'd']
        self.assertEqual(get_query_result(q, None), ['a', 'b', 'c', 'd'])

        q = Q(['a', 'b']) + [Q('c'), Q('d')]
        self.assertEqual(get_query_result(q, None), ['a', 'b', 'c', 'd'])

        q = Q('%(A)s: %(B)s') % {'A': 'a', 'B': 'b'}
        self.assertEqual(get_query_result(q, None), 'a: b')

        q = Q('%(A)s: %(B)s') % {Q('A'): Q('a'), Q('B'): Q('b')}
        self.assertEqual(get_query_result(q, None), 'a: b')

class ReprTest(unittest.TestCase):
    def test_reprs(self):
        # Operators
        self.assertEqual(repr(Q(4) + Q(5)), '4 + 5')
        self.assertEqual(repr(Q(4) - Q(5)), '4 - 5')
        self.assertEqual(repr(Q(4) * Q(5)), '4 * 5')
        self.assertEqual(repr(Q(4) / Q(5)), '4 / 5')

        # Booleans
        self.assertEqual(repr(Q(4) | ~ Q(5)), '4 | ~ 5')
        self.assertEqual(repr(Q(4) & ~ Q(5)), '4 & ~ 5')

        # Attributes and calls
        self.assertEqual(repr(Q.a), 'Q.a')
        self.assertEqual(repr(Q.b['lookup']), "Q.b['lookup']")
        self.assertEqual(repr(Q.a.call('param') + Q.b['lookup']), "Q.a.call('param') + Q.b['lookup']")
        self.assertEqual(repr(Q.a.call('param', 'p2', key='value')), "Q.a.call('param', 'p2', key='value')")
        self.assertEqual(repr(Q.a.call(Q.a)), "Q.a.call(Q.a)")


class InContextTest(unittest.TestCase):
    """
    Evaluation of expressions, on a context object.
    (The context is usually a Node in practise.)
    """
    def setUp(self):
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
        self.obj = obj

    def test_q_attribute_selection(self):
        # Combinations of attribute lookups, __getitem__ and calling.
        q = Q.value
        self.assertEqual(get_query_result(q, self.obj), 'value')

        q = Q['attr']
        self.assertEqual(get_query_result(q, self.obj), 'item attr')

        q = Q.action()
        self.assertEqual(get_query_result(q, self.obj), 'action-result')

        q = Q.nested_obj.action()
        self.assertEqual(get_query_result(q, self.obj), 'action-result')

        q = Q.nested_obj.action()
        self.assertEqual(get_query_result(q, self.obj), 'action-result')

        q = Q.nested_obj.nested_obj['attr']
        self.assertEqual(get_query_result(q, self.obj), 'item attr')

        # Add some operators
        q = Q.nested_obj.nested_obj.value + '-' + Q.value
        self.assertEqual(get_query_result(q, self.obj), 'value-value')

        q = ~ Q.true()
        self.assertEqual(get_query_result(q, self.obj), False)

        q = Q.true() & Q.nested_obj.true()
        self.assertEqual(get_query_result(q, self.obj), True)

        q = Q.true() | Q.nested_obj.false()
        self.assertEqual(get_query_result(q, self.obj), True)

    def test_query_result(self):
        """
        Analysis of the following hierarchical query.

        # Q                               | <q_object_test.Obj object at 0x976d64c>
        # Q.true                          | <bound method Obj.true of <q_object_test.Obj object at 0x976d64c>>
        # Q.true()                        | True
        # Q                               | <q_object_test.Obj object at 0x976d64c>
        # Q.nested_obj                    | <q_object_test.Obj object at 0x976d64c>
        # Q.nested_obj.false              | <bound method Obj.false of <q_object_test.Obj object at 0x976d64c>>
        # Q.nested_obj.false()            | False
        # Q.true() | Q.nested_obj.false() | True
        """
        def count(query):
            result = query._execute_query(self.obj)
            return len(list(result.walk_through_subqueries()))

        # Check subquery count
        q = Q
        self.assertEqual(count(q), 1)

        q = Q.true
        self.assertEqual(count(q), 2)

        q = Q.true()
        self.assertEqual(count(q), 3)

        q = Q.nested_obj
        self.assertEqual(count(q), 2)

        q = Q.nested_obj.false
        self.assertEqual(count(q), 3)

        q = Q.nested_obj.false()
        self.assertEqual(count(q), 4)

        q = Q.true() | Q.nested_obj.false()
        self.assertEqual(count(q), 8)

        # Check subquery order.
        q = Q.true() | Q.nested_obj.false()
        result = q._execute_query(self.obj)
        self.assertIsInstance(result, QueryResult)

            # The first parameter contains all the subqueries that are executed.
        queries = [ r[0] for r in result.walk_through_subqueries() ]
        self.assertEqual(map(repr, queries), [
                 'Q',
                 'Q.true',
                 'Q.true()',
                 'Q',
                 'Q.nested_obj',
                 'Q.nested_obj.false',
                 'Q.nested_obj.false()',
                 'Q.true() | Q.nested_obj.false()' ])

        for q in queries:
            self.assertIsInstance(q, Query)

            # The second parameter contains the results for the respective subqueries.
        results = [ r[1] for r in result.walk_through_subqueries() ]
        self.assertEqual(results[2], True)
        self.assertEqual(results[6], False)
        self.assertEqual(results[7], True)


class InActionTest(unittest.TestCase):
    def test_q_navigation(self):
        this = self
        class DummyException(Exception):
            pass

        class MyNode(Node):
            class Hosts:
                host = LocalHost

            # 1. Normal query from node.
            attr = 'value'
            query = Q.attr
            query2 = Q.attr + Q.attr

            def my_action(self):
                return self.query

            # 2. Exception in query from node.

            @property
            def this_raises(self):
                raise DummyException

            query3 = Q.this_raises + Q.attr

            def my_action2(self):
                # Calling query3 raises a QueryException
                # The inner exception that one is the DummyException
                try:
                    return self.query3
                except Exception as e:
                    this.assertIsInstance(e, ActionException)

                    this.assertIsInstance(e.inner_exception, QueryException)
                    this.assertIsInstance(e.inner_exception.node, MyNode)
                    this.assertIsInstance(e.inner_exception.query, Query)

                    this.assertIsInstance(e.inner_exception.inner_exception, DummyException)

                    # Raising the exception again at this point, will turn it
                    # into an action exception.
                    raise

        s = MyNode()
        env = Env(s)

        # 1.
        self.assertEqual(env.my_action(), 'value')
        self.assertEqual(env.query2, 'valuevalue')

        # 2.
        self.assertRaises(ActionException, env.my_action2)
        try:
            env.my_action2()
        except Exception as e:
            self.assertIsInstance(e, ActionException)

