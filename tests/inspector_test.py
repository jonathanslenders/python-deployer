import unittest

from deployer.query import Q
from deployer.node import Node, SimpleNode, Env
from deployer.groups import Production, Staging, production, staging
from deployer.pseudo_terminal import Pty, DummyPty
from deployer.loggers import LoggerInterface
from deployer.node import map_roles, dont_isolate_yet, required_property, alias
from deployer.inspection import Inspector
from deployer.host_container import HostsContainer

from our_hosts import LocalHost, LocalHost1, LocalHost2, LocalHost3, LocalHost4, LocalHost5

class InspectorTest(unittest.TestCase):
    def test_node_inspection(self):
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

        s = Root()
        insp = Inspector(s)

        # get_childnodes and get_actions
        self.assertEqual(repr(insp.get_childnodes()), '[<Node Root.A>, <Node Root.B>]')
        self.assertEqual(repr(insp.get_actions()), '[<Action Root.a>, <Action Root.b>, <Action Root.c>]')
        for a in insp.get_actions():
            self.assertIn(a.name, ['a', 'b', 'c'])

        # has_childnode and get_childnode
        self.assertEqual(insp.has_childnode('A'), True)
        self.assertEqual(insp.has_childnode('C'), False)
        self.assertEqual(repr(insp.get_childnode('A')), '<Node Root.A>')
        self.assertRaises(AttributeError, insp.get_childnode, 'unknown_childnode')

        # has_action and get_action
        self.assertEqual(insp.has_action('a'), True)
        self.assertEqual(insp.has_action('d'), False)
        self.assertEqual(repr(insp.get_action('a')), '<Action Root.a>')
        self.assertRaises(AttributeError, insp.get_action, 'unknown_action')

        # get_path
        self.assertEqual(repr(Inspector(s.A).get_path()), "('Root', 'A')")
        self.assertEqual(repr(Inspector(s.B.C).get_path()), "('Root', 'B', 'C')")

        # get_name and get_full_name
        self.assertEqual(Inspector(s.A).get_name(), 'A')
        self.assertEqual(Inspector(s.B.C).get_name(), 'C')

        self.assertEqual(Inspector(s.A).get_full_name(), 'Root.A')
        self.assertEqual(Inspector(s.B.C).get_full_name(), 'Root.B.C')

        # is_callable
        self.assertEqual(Inspector(s.A).is_callable(), False)
        self.assertEqual(Inspector(s.B.C).is_callable(), True)

        # Inspector.__repr__
        self.assertEqual(repr(Inspector(s)), 'Inspector(node=Root)')
        self.assertEqual(repr(Inspector(s.B.C)), 'Inspector(node=Root.B.C)')

        # get_group
        self.assertEqual(Inspector(s.A).get_group(), Production)
        self.assertEqual(Inspector(s.B).get_group(), Staging)
        self.assertEqual(Inspector(s.B.C).get_group(), Staging)

        # walk
        self.assertEqual(len(list(insp.walk())), 4)
        self.assertEqual({ Inspector(i).get_name() for i in insp.walk() }, { 'Root', 'A', 'B', 'C' })
        for i in insp.walk():
            self.assertIsInstance(i, Node)

    def test_node_inspection_on_env_object(self):
        class Root(Node):
            class A(Node):
                pass
            class B(Node):
                def action(self):
                    return 'action-b'
            def action(self):
                return 'action-root'

        s = Root()
        env = Env(Root())
        insp = Inspector(env)
        self.assertEqual(repr(insp.get_childnodes()), '[Env(Root.A), Env(Root.B)]')
        self.assertEqual(insp.get_childnode('B').action(), 'action-b')

        # Walk
        self.assertEqual(len(list(insp.walk())), 3)
        self.assertEqual({ Inspector(i).get_name() for i in insp.walk() }, { 'Root', 'A', 'B' })
        for i in insp.walk():
            self.assertIsInstance(i, Env)

    def test_iter_isolations(self):
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

        # Inspection on Env and Node objects
        def test(insp, type):
            self.assertEqual(len(list(insp.iter_isolations())), 9) # 3x3

            # Inspection on env should yield Env objects, Node should yield
            # node objects.
            for i, node in insp.iter_isolations():
                self.assertIsInstance(node, type)

        test(Inspector(A().B.C.D), Node)
        test(Inspector(Env(A()).B.C.D), Env)