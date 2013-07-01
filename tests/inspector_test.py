import unittest

from deployer.query import Q
from deployer.node import Node, SimpleNode, Env
from deployer.groups import Production, Staging, production, staging
from deployer.pseudo_terminal import Pty, DummyPty
from deployer.loggers import LoggerInterface
from deployer.node import map_roles, dont_isolate_yet, required_property, alias
from deployer.inspection import Inspector, PathType
from deployer.inspection.inspector import NodeIterator
from deployer.inspection import filters
from deployer.host_container import HostsContainer

from our_hosts import LocalHost, LocalHost1, LocalHost2, LocalHost3, LocalHost4, LocalHost5

class InspectorTest(unittest.TestCase):
    def setUp(self):
        class Root(Node):
            @production
            class A(Node):
                pass
            @staging
            class B(Node):
                class C(Node):
                    def __call__(self):
                        # __call__ is the default action
                        pass
            def a(self): pass
            def b(self): pass
            def c(self): pass
            c.__name__ = 'another-name' # Even if we override this name, Action.name should remain 'c'

        self.s = Root()
        self.insp = Inspector(self.s)

    def test_get_childnodes(self):
        insp = self.insp
        self.assertEqual(repr(insp.get_childnodes()), '[<Node Root.A>, <Node Root.B>]')
        self.assertEqual(repr(insp.get_actions()), '[<Action Root.a>, <Action Root.b>, <Action Root.c>]')
        for a in insp.get_actions():
            self.assertIn(a.name, ['a', 'b', 'c'])

    def test_has_childnodes(self):
        insp = self.insp
        self.assertEqual(insp.has_childnode('A'), True)
        self.assertEqual(insp.has_childnode('C'), False)
        self.assertEqual(repr(insp.get_childnode('A')), '<Node Root.A>')
        self.assertRaises(AttributeError, insp.get_childnode, 'unknown_childnode')

    def test_has_action(self):
        insp = self.insp
        self.assertEqual(insp.has_action('a'), True)
        self.assertEqual(insp.has_action('d'), False)
        self.assertEqual(repr(insp.get_action('a')), '<Action Root.a>')
        self.assertRaises(AttributeError, insp.get_action, 'unknown_action')

    def test_get_path(self):
        s = self.s
        self.assertEqual(repr(Inspector(s.A).get_path()), "('Root', 'A')")
        self.assertEqual(repr(Inspector(s.B.C).get_path()), "('Root', 'B', 'C')")
        self.assertEqual(repr(Inspector(s.B.C).get_path(path_type=PathType.NODE_AND_NAME)),
                        "((<Node Root>, 'Root'), (<Node Root.B>, 'B'), (<Node Root.B.C>, 'C'))")
        self.assertEqual(repr(Inspector(s.B.C).get_path(path_type=PathType.NODE_ONLY)),
                        "(<Node Root>, <Node Root.B>, <Node Root.B.C>)")

    def test_get_name(self):
        s = self.s
        self.assertEqual(Inspector(s.A).get_name(), 'A')
        self.assertEqual(Inspector(s.B.C).get_name(), 'C')

        self.assertEqual(Inspector(s.A).get_full_name(), 'Root.A')
        self.assertEqual(Inspector(s.B.C).get_full_name(), 'Root.B.C')

    def test_is_callable(self):
        s = self.s
        self.assertEqual(Inspector(s.A).is_callable(), False)
        self.assertEqual(Inspector(s.B.C).is_callable(), True)

    def test_repr(self):
        s = self.s
        self.assertEqual(repr(Inspector(s)), 'Inspector(node=Root)')
        self.assertEqual(repr(Inspector(s.B.C)), 'Inspector(node=Root.B.C)')

    def test_get_group(self):
        s = self.s
        self.assertEqual(Inspector(s.A).get_group(), Production)
        self.assertEqual(Inspector(s.B).get_group(), Staging)
        self.assertEqual(Inspector(s.B.C).get_group(), Staging)

    def test_walk(self):
        insp = self.insp
        self.assertEqual(len(list(insp.walk())), 4)
        self.assertEqual({ Inspector(i).get_name() for i in insp.walk() }, { 'Root', 'A', 'B', 'C' })
        for i in insp.walk():
            self.assertIsInstance(i, Node)

    def test_walk_from_childnode(self):
        s = self.s
        insp = Inspector(s.B)
        self.assertEqual(len(list(insp.walk())), 2)
        self.assertEqual({ Inspector(i).get_name() for i in insp.walk() }, { 'B', 'C' })

class InspectorOnEnvTest(unittest.TestCase):
    def setUp(self):
        class Root(Node):
            class A(Node):
                pass
            class B(Node):
                def action(self):
                    return 'action-b'
            def action(self):
                return 'action-root'
            def action2(self):
                return 'action-root2'

        self.env = Env(Root())
        self.insp = Inspector(self.env)

    def test_get_childnodes(self):
        insp = self.insp
        self.assertEqual(repr(insp.get_childnodes()), '[Env(Root.A), Env(Root.B)]')
        self.assertEqual(insp.get_childnode('B').action(), 'action-b')

    def test_get_actions(self):
        insp = self.insp
        self.assertEqual(len(insp.get_actions()), 2)
        self.assertEqual(repr(insp.get_action('action')), '<Env.Action Root.action>')
        self.assertEqual(insp.get_action('action')(), 'action-root')
        self.assertEqual(insp.get_action('action').name, 'action')

    def test_walk(self):
        insp = self.insp
        self.assertEqual(len(list(insp.walk())), 3)
        self.assertEqual({ Inspector(i).get_name() for i in insp.walk() }, { 'Root', 'A', 'B' })
        for i in insp.walk():
            self.assertIsInstance(i, Env)

class InspectorTestIterIsolations(unittest.TestCase):
    def setUp(self):
        class A(Node):
            class Hosts:
                role1 = LocalHost1, LocalHost2, LocalHost3
                role2 = LocalHost2, LocalHost4, LocalHost5

            @map_roles('role1', extra='role2')
            class B(SimpleNode.Array):
                class C(Node):
                    @map_roles('extra')
                    class D(SimpleNode.Array):
                        pass
        self.A = A

    def test_inspection_env_node(self):
        A = self.A
        def test(insp, type):
            self.assertEqual(len(list(insp.iter_isolations())), 9) # 3x3

            # Inspection on env should yield Env objects, Node should yield
            # node objects.
            for i, node in insp.iter_isolations():
                self.assertIsInstance(node, type)

            # Test get_isolation
            node = insp.get_isolation((0, 0))
            self.assertIsInstance(node, type)
            self.assertEqual(repr(node),
                '<Node A.B[0].C.D[0]>' if type == Node else 'Env(A.B[0].C.D[0])')

            node = insp.get_isolation((2, 2))
            self.assertIsInstance(node, type)
            self.assertEqual(repr(node),
                '<Node A.B[2].C.D[2]>' if type == Node else 'Env(A.B[2].C.D[2])')

        test(Inspector(A().B.C.D), Node)
        test(Inspector(Env(A()).B.C.D), Env)

class InspectorIteratorTest(unittest.TestCase):
    def setUp(self):
        class Base(Node):
            pass

        self.Base = Base

        class A(Node):
            def my_action(self): return 'a'

            class B(Base):
                def my_action(self): return 'b'
                def my_other_action(self): return 'b2'

                class C(SimpleNode.Array):
                    class Hosts:
                        host = LocalHost1, LocalHost2, LocalHost3, LocalHost4

                    def my_action(self): return 'c'

                    class E(Base):
                        def my_action(self): return 'e'

            class D(Base):
                def my_action(self): return 'd'
                def my_other_action(self): return 'd2'

            class _P(Base):
                # A private node
                def my_action(self): return '_p'

        self.env = Env(A())
        self.insp = Inspector(self.env)

    def test_walk(self):
        insp = self.insp
        Base = self.Base
        self.assertEqual(len(insp.walk()), 6)
        self.assertIsInstance(insp.walk(), NodeIterator)
        self.assertEqual(len(insp.walk().filter(filters.IsInstance(Base))), 4)

    def test_walk_public_only(self):
        insp = self.insp
        self.assertEqual(len(insp.walk(filters.PublicOnly)), 5)
        self.assertEqual(len(insp.walk().filter(filters.PublicOnly)), 5)

    def test_walk_private_only(self):
        insp = self.insp
        self.assertEqual(len(insp.walk(filters.PrivateOnly)), 1)

    def test_or_operation(self):
        insp = self.insp
        self.assertEqual(len(insp.walk(filters.PrivateOnly | filters.HasAction('my_other_action'))), 3)
        self.assertEqual({ repr(n) for n in insp.walk(filters.PrivateOnly | filters.HasAction('my_other_action')) },
                { 'Env(A.B)', 'Env(A.D)', 'Env(A._P)' })

        # Check repr
        self.assertEqual(repr(filters.PrivateOnly | filters.HasAction('my_other_action')),
                "PrivateOnly | HasAction('my_other_action')")

    def test_and_operation(self):
        insp = self.insp
        self.assertEqual(len(insp.walk(filters.PrivateOnly & filters.IsInstance(self.Base))), 1)

        # Check repr (xxx: maybe this is not the cleanest one.)
        self.assertEqual(repr(filters.PrivateOnly & filters.IsInstance(self.Base)),
                "PrivateOnly & IsInstance(<class 'inspector_test.Base'>)")

    def test_call_action(self):
        insp = self.insp
        Base = self.Base
        result = list(insp.walk().filter(filters.IsInstance(Base)).call_action('my_action'))
        self.assertEqual(len(result), 7)
        self.assertEqual(set(result), { 'b', 'd', '_p', 'e', 'e', 'e', 'e' })

    def test_filter_on_action(self):
        insp = self.insp
        result = insp.walk().filter(filters.HasAction('my_action'))
        self.assertEqual(len(result), 6)
        result = insp.walk().filter(filters.HasAction('my_other_action'))
        self.assertEqual(len(result), 2)
        result = insp.walk().filter(filters.HasAction('my_other_action')).call_action('my_other_action')
        self.assertEqual(set(result), { 'b2', 'd2' })

    def test_prefer_isolation(self):
        insp = self.insp
        env = self.env
        result = insp.walk().prefer_isolation(LocalHost2)
        self.assertEqual( set(repr(e) for e in result),
                    { repr(e) for e in { env, env.B, env.D, env._P, env.B.C[LocalHost2], env.B.C[LocalHost2].E }})

        # Maybe we should also implement a better Node.__eq__ and Env.__eq__, then we can do this:
        # >> self.assertEqual(set(result), { env, env.B, env.D, env.B.C[LocalHost2], env.B.C[LocalHost2].E })

    def test_multiple_iterator(self):
        insp = self.insp
        node_iterator = insp.walk()
        self.assertEqual(len(list(node_iterator)), 6)
        self.assertEqual(len(list(node_iterator)), 6)
        self.assertEqual(len(node_iterator), 6)
        self.assertEqual(len(node_iterator), 6)

    def test_unknown_action(self):
        insp = self.insp
        self.assertRaises(AttributeError, lambda: list(insp.walk().call_action('my_action2')))
