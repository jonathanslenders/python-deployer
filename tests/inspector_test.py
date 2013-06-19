import unittest

from deployer.query import Q
from deployer.node import Node, SimpleNode, Env
from deployer.pseudo_terminal import Pty, DummyPty
from deployer.loggers import LoggerInterface
from deployer.node import Inspector, map_roles, dont_isolate_yet, required_property, alias
from deployer.host_container import HostsContainer

from our_hosts import LocalHost, LocalHost1, LocalHost2, LocalHost3, LocalHost4, LocalHost5

class InspectorTest(unittest.TestCase):
    def test_node_inspection(self):
        class Root(Node):
            class A(Node):
                pass
            class B(Node):
                class C(Node):
                    def __call__(self):
                        # __call__ is the default action
                        pass
            def a(self): pass
            def b(self): pass
            def c(self): pass

        s = Root()
        insp = Inspector(s)

        # get_childnodes and get_actions
        self.assertEqual(repr(insp.get_childnodes()), '[<Node Root.A>, <Node Root.B>]')
        self.assertEqual(repr(insp.get_actions()), '[<Action Root.a>, <Action Root.b>, <Action Root.c>]')

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
        self.assertEqual(repr(Inspector(s.A).get_path()), "[(<Node Root>, 'Root'), (<Node Root.A>, 'A')]")
        self.assertEqual(repr(Inspector(s.B.C).get_path()), "[(<Node Root>, 'Root'), (<Node Root.B>, 'B'), (<Node Root.B.C>, 'C')]")

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
