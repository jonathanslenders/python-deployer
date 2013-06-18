import unittest

from deployer.query import Q
from deployer.node import Node, SimpleNode, Env
from deployer.host import LocalHost
from deployer.pty import Pty, DummyPty
from deployer.loggers import LoggerInterface
from deployer.node import Inspector, map_roles, dont_isolate_yet, required_property, alias
from deployer.host_container import HostsContainer


class LocalHost1(LocalHost):
    # Act as another host then localhost
    slug = 'localhost1'

class LocalHost2(LocalHost):
    # Act as another host then localhost
    slug = 'localhost2'

class LocalHost3(LocalHost):
    # Act as another host then localhost
    slug = 'localhost3'

class LocalHost4(LocalHost):
    # Act as another host then localhost
    slug = 'localhost4'

class LocalHost5(LocalHost):
    # Act as another host then localhost
    slug = 'localhost5'


class NodeTest(unittest.TestCase):
    def test_assignments_to_node(self):
        """
        When a Node is assigned to a Node class, retrieval
        should return the same object.
        """
        class MyNode(Node):
            pass
        class S2(Node):
            pass

        MyNode.s = S2
        self.assertEqual(MyNode.s, S2) # TODO: the same for methods is not true!!!

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

    def test_node_initialisation(self):
        class S(Node):
            class Hosts:
                role1 = LocalHost
                role2 = LocalHost

        s = S()
        self.assertEqual(isinstance(s, Node), True)
        self.assertEqual(s.hosts.roles, ['role1', 'role2'])

    def test_nesting(self):
        class S(Node):
            class Hosts:
                role1 = LocalHost
                role2 = LocalHost

            class T(Node):
                pass

            class U(Node):
                pass

        s = S()
        self.assertEqual(isinstance(s, Node), True)
        self.assertEqual(isinstance(s.T, Node), True)
        self.assertEqual(isinstance(s.U, Node), True)

        self.assertEqual(s.hosts.roles, ['role1', 'role2'])
        self.assertEqual(s.T.hosts.roles, ['role1', 'role2'])
        self.assertEqual(s.U.hosts.roles, ['role1', 'role2'])

        self.assertEqual(s.hosts, s.T.hosts)
        self.assertEqual(s.hosts, s.U.hosts)

    def test_mapping(self):
        class S(Node):
            class Hosts:
                role1 = LocalHost
                role2 = LocalHost2

            @map_roles(role3='role1', role4='role2', role5='role3', role6=['role1', 'role2'])
            class T(Node):
                pass

            @map_roles(role7=['role1', 'role3'], role8='role1')
            class U(Node):
                class V(Node):
                    pass

                @map_roles(role9='role1', role10='role7')
                class W(Node):
                    pass

                class X(Node):
                    class Hosts:
                        role1 = LocalHost3
                        role2 = [ LocalHost4, LocalHost5 ]

                @map_roles(role11='role7')
                class Y(Node):
                    # Because of map_roles, the following will be overriden.
                    class Hosts:
                        role1 = LocalHost1

        s = S()
        self.assertEqual(isinstance(s, Node), True)
        self.assertEqual(isinstance(s.T, Node), True)
        self.assertEqual(isinstance(s.U, Node), True)
        self.assertEqual(isinstance(s.U.V, Node), True)
        self.assertEqual(isinstance(s.U.W, Node), True)
        self.assertEqual(isinstance(s.U.X, Node), True)
        self.assertEqual(isinstance(s.U.Y, Node), True)

        self.assertEqual(s.hosts.roles, ['role1', 'role2'])
        self.assertEqual(s.T.hosts.roles, ['role3', 'role4', 'role5', 'role6'])
        self.assertEqual(s.U.hosts.roles, ['role7', 'role8'])
        self.assertEqual(s.U.V.hosts.roles, ['role7', 'role8'])
        self.assertEqual(s.U.W.hosts.roles, ['role10', 'role9']) # Lexical ordered
        self.assertEqual(s.U.X.hosts.roles, ['role1', 'role2'])
        self.assertEqual(s.U.X.hosts.roles, ['role1', 'role2'])
        self.assertEqual(s.U.Y.hosts.roles, ['role11'])

        self.assertEqual(s.T.hosts, HostsContainer({ 'role3': LocalHost, 'role4': LocalHost2, 'role5': [], 'role6': [ LocalHost, LocalHost2 ] }))
        self.assertEqual(s.U.hosts, HostsContainer({ 'role7': LocalHost, 'role8': LocalHost }))
        self.assertEqual(s.U.V.hosts, HostsContainer({ 'role7': LocalHost, 'role8': LocalHost }))
        self.assertEqual(s.U.W.hosts, HostsContainer({ 'role9': [], 'role10': LocalHost }))
        self.assertEqual(s.U.X.hosts, HostsContainer({ 'role1': LocalHost3, 'role2': [ LocalHost4, LocalHost5] }))
        self.assertEqual(s.U.Y.hosts, HostsContainer({ 'role11': LocalHost }))

    def test_invalid_mapping(self):
        class NotANode(object): pass
        self.assertRaises(TypeError, map_roles('role'), NotANode())

    def test_env_object(self):
        class S(Node):
            class Hosts:
                role1 = LocalHost
                role2 = LocalHost2

            def my_action(self):
                return 'result'

            def return_name_of_self(self):
                return self.__class__.__name__

            def echo_on_all(self):
                return self.hosts.run('/bin/echo echo', interactive=False)

            def echo_on_role1(self):
                return self.hosts.filter('role1').run('/bin/echo echo', interactive=False)

            def echo_on_role2(self):
                return self.hosts.get('role2').run('/bin/echo echo', interactive=False)

        s = S()
        env = Env(s)

        self.assertEqual(env.my_action(), 'result')
        self.assertEqual(env.return_name_of_self(), 'Env')
        self.assertEqual(env.echo_on_all(), [ 'echo\r\n', 'echo\r\n' ])
        self.assertEqual(env.echo_on_role1(), [ 'echo\r\n' ])
        self.assertEqual(env.echo_on_role2(), 'echo\r\n')

        # Isinstance hooks
        self.assertIsInstance(s, S)
        self.assertIsInstance(env, S)

    def test_bin_false(self):
        class S(Node):
            class Hosts:
                role1 = LocalHost

            def return_false(self):
                return self.hosts.run('/bin/false', interactive=False)

        s = S()
        env = Env(s)

        from deployer.exceptions import ExecCommandFailed
        self.assertRaises(ExecCommandFailed, env.return_false) # TODO: maybe this should be wrapped in an ActionFailed.

    def test_action_with_params(self):
        class MyNode(Node):
            class Hosts:
                host = LocalHost

            def my_action(self, param1, *a, **kw):
                return (param1, a, kw)

        s = MyNode()
        env = Env(s)
        result = env.my_action('param1', 1, 2, k=3, v=4)
        self.assertEqual(result, ('param1', (1, 2), { 'k': 3, 'v': 4 }) )

    def test_nested_action(self):
        class MyNode(Node):
            class Node2(Node):
                class Node3(Node):
                    def my_action(self):
                        return 'result'

        env = Env(MyNode())
        result = env.Node2.Node3.my_action()
        self.assertEqual(result, 'result')

    def test_property(self):
        class MyNode(Node):
            class Hosts:
                host = LocalHost

            @property
            def p(self):
                return 'value'

            def my_action(self):
                return self.p

        s = MyNode()
        env = Env(s)
        self.assertEqual(env.my_action(), 'value')

    def test_wrapping_middle_node_in_env(self):
        class S(Node):
            class Hosts:
                role1 = LocalHost1, LocalHost2

            class T(Node):
                def action(self):
                    return len(self.hosts)

        s = S()
        env = Env(s.T)
        self.assertEqual(env.action(), 2)

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

    def test_attribute_overrides(self):
        # Test double underscore overrides.
        class N(Node):
            class O(Node):
                value = 'original_value'

        self.assertEqual(N.O.value, 'original_value')

        class N2(N):
            O__value = 'new_value'

            def O__func(self):
                return 'return_value'

        self.assertEqual(N2.O.value, 'new_value')

        env = Env(N2())
        self.assertEqual(env.O.value, 'new_value')
        self.assertEqual(env.O.func(), 'return_value')

    def test_multiple_level_overrides(self):
        class N(Node):
            class O(Node):
                class P(Node):
                    class Q(Node):
                        value = 'original_value'

        self.assertEqual(N.O.P.Q.value, 'original_value')

        class N2(N):
            O__P__Q__value = 'new_value'

            def O__P__func(self):
                return 'return_value'

        self.assertEqual(N2.O.P.Q.value, 'new_value')

        env = Env(N2())
        self.assertEqual(env.O.P.Q.value, 'new_value')
        self.assertEqual(env.O.P.func(), 'return_value')

    def test_unknown_attribute_override(self):
        class N(Node):
            class O(Node):
                pass
        # Using this attributes in a class inheriting from here should raise an exception3
        # TODO: correct exception.
        self.assertRaises(Exception, type, 'NewN', (N,), { 'unknown__member': True })
        self.assertRaises(Exception, type, 'NewN', (N,), { 'O__unknown__member': True })

    def test_simple_node(self):
        class N(SimpleNode):
            class Hosts:
                host = LocalHost1, LocalHost2

            def func(self):
                return 'result'

        # SimpleNode executes for each host separately.
        env = Env(N())
        self.assertEqual(env.func(), ['result', 'result' ])

    def test_simple_node_getitem(self):
        class N(SimpleNode):
            class Hosts:
                host = LocalHost1, LocalHost2

            def func(self):
                return 'result'

        n = N()
        self.assertIsInstance(n[0], SimpleNode)
        self.assertIsInstance(n[1], SimpleNode)
        self.assertIsInstance(n[LocalHost1], SimpleNode)
        self.assertIsInstance(n[LocalHost2], SimpleNode)
        self.assertEqual(n[0]._isolated, True)
        self.assertEqual(n[1]._isolated, True)
        self.assertEqual(n[LocalHost1]._isolated, True)
        self.assertEqual(n[LocalHost2]._isolated, True)
        self.assertRaises(IndexError, lambda: n[2])
        self.assertRaises(IndexError, lambda: n[LocalHost3])

        # Calling the isolated item should not return an array
        env = Env(N())
        self.assertEqual(env.func(), ['result', 'result' ])
        self.assertEqual(env[0].func(), 'result')
        self.assertEqual(env[1].func(), 'result')
        self.assertRaises(IndexError, lambda: env[2])
        self.assertRaises(IndexError, lambda: env[LocalHost3])

    def test_getitem_on_normal_node(self):
        # __getitem__ should not be possible on a normal node.
        class N(Node):
            class Hosts:
                host = LocalHost1, LocalHost2
        n = N()
        self.assertRaises(TypeError, lambda:n[0])

    def test_getitem_between_simplenodes(self):
        # We often go from one simplenode to another one by using
        # self.host as the index parameter.
        class Root(Node):
            class Hosts:
                role = LocalHost1, LocalHost2

            @map_roles('role')
            class A(SimpleNode.Array):
                def action(self):
                    return self.parent.B[self.host].action()

            @map_roles('role')
            class B(SimpleNode.Array):
                def action(self):
                    return '%s in b' % self.host.slug

        env = Env(Root())
        self.assertEqual(set(env.A.action()), set(['localhost2 in b', 'localhost1 in b']))
        self.assertIn(env.A[0].action(), ['localhost1 in b', 'localhost2 in b'])

    def test_dont_isolate_yet(self):
        once = [0]
        for_each_host = [0]
        this = self

        class A(Node):
            class Hosts:
                my_role = LocalHost1, LocalHost2

            @map_roles('my_role')
            class B(SimpleNode.Array):
                def for_each_host(self):
                    for_each_host[0] += 1
                    this.assertEqual(len(self.hosts), 1)

                @dont_isolate_yet
                def only_once(self):
                    once[0] += 1
                    self.for_each_host()
                    this.assertEqual(len(self.hosts), 2)
                    return 'result'

        env = Env(A())
        result = env.B.only_once()

        self.assertEqual(result, 'result')
        self.assertEqual(once, [1])
        self.assertEqual(for_each_host, [2])

    def test_nested_simple_nodes(self):
        class N(SimpleNode):
            class Hosts:
                host = LocalHost1, LocalHost2

            class M(SimpleNode):
                def func(self):
                    return 'result'

        # `M` gets both hosts as well.
        env = Env(N())
        self.assertEqual(env.M.func(), ['result', 'result' ])

    def test_simple_nodes_in_normal_node(self):
        class N(Node):
            class Hosts:
                role1 = LocalHost1, LocalHost
                role2 = LocalHost3

            @map_roles('role1')
            class M(SimpleNode.Array):
                def func(self):
                    return 'func-m'

                class X(SimpleNode):
                    def func(self):
                        return 'func-x'

            def func(self):
                return 'func-n'

        # `M` should behave as an array.
        env = Env(N())
        self.assertEqual(env.func(), 'func-n')
        self.assertEqual(env.M.func(), ['func-m', 'func-m' ])
        self.assertEqual(env.M[0].func(), 'func-m')
        self.assertEqual(env.M.X.func(), ['func-x', 'func-x'])
        self.assertEqual(env.M[0].X.func(), 'func-x')
        self.assertEqual(env.M.X[0].func(), 'func-x')

    def test_calling_between_simple_and_normal_nodes(self):
        class N(Node):
            class Hosts:
                role1 = LocalHost1, LocalHost
                role2 = LocalHost3

            def do_tests(this):
                self.assertEqual(this.M.func(), ['func-m', 'func-m'])
                self.assertEqual(this.M.X.func(), ['func-x', 'func-x'])
                self.assertEqual(this.M[0].func(), 'func-m')
                self.assertEqual(this.M.X[0].func(), 'func-x')

            def func(this):
                return 'func-n'

            @map_roles(host='role1')
            class M(SimpleNode.Array):
                def func(this):
                    return 'func-m'

                class X(SimpleNode):
                    def func(this):
                        return 'func-x'

                    def do_tests(this):
                        self.assertEqual(this.func(), 'func-x')
                        self.assertEqual(this.parent.parent.func(), 'func-n')
                        self.assertEqual(this.parent.parent.M.func(), ['func-m', 'func-m'])
                        self.assertEqual(this.parent.parent.M[0].func(), 'func-m')

        env = Env(N())
        env.do_tests()
        env.M.X.do_tests()

    def test_node_names(self):
        class Another(Node):
            pass

        class N(Node):
            class Hosts:
                role1 = LocalHost1, LocalHost
                role2 = LocalHost3

            class M(Node):
                class O(Node):
                    pass

            @map_roles(host='role1')
            class P(SimpleNode.Array):
                pass

            class another_node(Another):
                pass

            another_node2 = Another

        # For the class definitions, the names don't change.
        self.assertEqual(N.__name__, 'N')
        self.assertEqual(N.M.__name__, 'M')
        self.assertEqual(N.M.O.__name__, 'O')
        self.assertEqual(N.P.__name__, 'P')
        self.assertEqual(N.another_node.__name__, 'another_node')
        self.assertEqual(N.another_node2.__name__, 'Another')

        # For instances (and mappings), they should be named according to the
        # full path.
        n = N()
        self.assertEqual(n.__class__.__name__, 'N')
        self.assertEqual(n.M.__class__.__name__, 'N.M')
        self.assertEqual(n.M.O.__class__.__name__, 'N.M.O')
        self.assertEqual(n.P.__class__.__name__, 'N.P')

        self.assertEqual(n.P[0].__class__.__name__, 'N.P[0]')
        self.assertEqual(n.P[1].__class__.__name__, 'N.P[1]')

        self.assertEqual(n.another_node.__class__.__name__, 'N.another_node')
        self.assertEqual(n.another_node2.__class__.__name__, 'N.another_node2')

        # Test Node.__repr__
        self.assertEqual(repr(n), '<Node N>')
        self.assertEqual(repr(n.M.O), '<Node N.M.O>')
        self.assertEqual(repr(n.P[1]), '<Node N.P[1]>')

        # Test Env.__repr__
        env = Env(n)
        self.assertEqual(repr(env), 'Env(N)')
        self.assertEqual(repr(env.M.O), 'Env(N.M.O)')
        self.assertEqual(repr(env.P[1]), 'Env(N.P[1])')

    def test_action_names(self):
        # Test Action.__repr__
        class N(Node):
            class M(Node):
                def my_action(self):
                    pass

        n = N()
        self.assertEqual(repr(n.M.my_action), '<Action N.M.my_action>')
        self.assertEqual(repr(N.M.my_action), '<Unbound Action my_action>')

    def test_nesting_normal_in_simple(self):
        # Node in simplenode
        def run():
            class A(SimpleNode):
                class B(SimpleNode):
                    class C(Node):
                        pass

        self.assertRaises(Exception, run) # TODO: correct exception

        # Simplenode in Node without using .Array
        def run():
            class A(Node):
                class B(SimpleNode):
                    pass

        self.assertRaises(Exception, run) # TODO: correct exception

        # .Array inside .Array
        def run():
            class A(Node.Array):
                class B(Node.Array):
                    pass

        self.assertRaises(Exception, run) # TODO: correct exception

    def test_invalid_mappings(self):
        # map_roles is required between Node and SimpleNode.Array
        def run():
            class A(Node):
                class B(SimpleNode.Array):
                    pass
        self.assertRaises(Exception, run) # TODO: correct exception

        # map_roles is not allowed between two SimpleNode classes.
        def run():
            class A(SimpleNode):
                @map_roles('my_role')
                class B(SimpleNode):
                    pass
        self.assertRaises(Exception, run) # TODO: correct exception

 #   def test_invalid_roles_in_simple_node(self):
 #       # It should not be possible to use any other role name than just 'host'
 #       # inside of a Simplenode.
 #       def run():
 #           class A(SimpleNode):
 #               class Hosts:
 #                   role1 = LocalHost1

 #       self.assertRaises(Exception, run) # TODO: correct exception

 #       def run():
 #           class A(Node):
 #               @map_roles(my_role='parent_role')
 #               class B(SimpleNode.Array):
 #                   pass

 #       self.assertRaises(Exception, run) # TODO: correct exception

    def test_invalid_hosts_object(self):
        # Hosts should be a role mapping or Hosts class definition
        # Anything else should raise an exception.
        def run():
            class MyNode(Node):
                Hosts = 4
        self.assertRaises(Exception, run) # TODO: correct exception

    def test_assignments_in_node(self):
        # It's not allowed to change attributes from a Node Environment.
        class MyNode(Node):
            def action(self):
                self.variable = 'value'

        env = Env(MyNode())
        self.assertRaises(AttributeError, env.action) # TODO: correct exception

    def test_custom_node_init(self):
        # It is not allowed to provide a custom __init__ method.
        def run():
            class MyNode(Node):
                def __init__(self, *a, **kw):
                    pass
        self.assertRaises(TypeError, run) # TODO: correct exception

    def test_running_actions_outside_env(self):
        # It should not be possible to run any action directly on the Node
        # without wrapping it in an Env object.
        class A(Node):
            def action(self):
                pass
        self.assertRaises(TypeError, A.action)

    def test_required_property(self):
        class A(Node):
            p = required_property()

            def action(self):
                self.p()
        env = Env(A())
        self.assertRaises(NotImplementedError, env.action)

    def test_action_aliases(self):
        # We can define multiple aliases for an action.
        class A(Node):
            @alias('my_alias2')
            @alias('my_alias')
            def action(self):
                return 'result'

        env = Env(A())
        self.assertEqual(env.action(), 'result')
        self.assertEqual(env.my_alias(), 'result')
        self.assertEqual(env.my_alias2(), 'result')

    def test_from_simple_to_parent_to_normal(self):
        # We had the issue that when moving from a SimpleNode (C) back up to A
        # (which is a normal Node), into B (which is also a normal Node). B
        # didn't took it's own Hosts, but instead received all the hosts from
        # A.
        this = self

        class A(Node):
            class Hosts:
                host = [ LocalHost1, LocalHost2, LocalHost3 ]

            class B(Node):
                class Hosts:
                    host = [ LocalHost4 ]

            @map_roles('host')
            class C(SimpleNode.Array):
                def test(self):
                    this.assertEqual(len(self.parent.B.hosts), 1)

        env = Env(A())
        env.C.test()

    def test_super_call(self):
        # Calling the superclass
        class A(Node):
            def action(self):
                return 'result'

        class B(A):
            def action(self):
                return 'The result was %s' % A.action(self)

        env = Env(B())
        self.assertEqual(env.action(), 'The result was result')

    def test_default_action(self):
        class A(Node):
            class Hosts:
                role = LocalHost1, LocalHost2

            def __call__(self):
                return 'A.call'

            class B(Node):
                def __call__(self):
                    return 'B.call'

            @map_roles('role')
            class C(SimpleNode.Array):
                def __call__(self):
                    return 'C.call'

        env = Env(A())
        self.assertEqual(env(), 'A.call')
        self.assertEqual(env.B(), 'B.call')
        self.assertEqual(env.C(), ['C.call', 'C.call'])
        self.assertEqual(env.C[0](), 'C.call')

    def test_going_from_isolated_to_parent(self):
        # When both B and C are a SimpleNode,
        # Going doing ``A.B.C[0].parent``, that should return a SimpleNode item.
        this = self

        class A(Node):
            class Hosts:
                role = LocalHost1, LocalHost2

            @map_roles('role')
            class B(SimpleNode.Array):
                def action2(self):
                    this.assertEqual(len(self.hosts), 1)
                    this.assertEqual(self._isolated, True)

                class C(SimpleNode):
                    def action(self):
                        this.assertEqual(len(self.hosts), 1)
                        self.parent.action2()

        env = Env(A())
        env.B.C.action()
        env.B.C[0].action()
        env.B.C[1].action()

    def test_initialize_node(self):
        class A(Node):
            class Hosts:
                role1 = LocalHost2
                role2 = LocalHost4, LocalHost5

            def action(self):
                # Define a new Node-tree
                class B(Node):
                    class Hosts:
                        role2 = self.hosts.filter('role2')

                    def action2(self):
                        return len(self.hosts)

                # Initialize it in the current Env, and call an action of that one.
                return self.initialize_node(B).action2()

        env = Env(A())
        self.assertEqual(env.action(), 2)

    def test_additional_roles_in_simple_node(self):
        # We should be able to pass additional roles to a SimpleNode, but
        # isolation happens at the 'host' role.
        this = self
        counter = [0]

        class A(Node):
            class Hosts:
                role1 = LocalHost1, LocalHost2, LocalHost3
                role2 = LocalHost2, LocalHost4, LocalHost5

            @map_roles('role1', extra='role2')
            class B(SimpleNode.Array):
                def action(self):
                    this.assertEqual(len(self.hosts.filter('host')), 1)
                    this.assertEqual(len(self.hosts.filter('extra')), 3)
                    this.assertEqual(set(self.hosts.roles), set(['host', 'extra']))
                    self.C.action2()
                    counter[0] += 1

                class C(SimpleNode):
                    def action2(self):
                        this.assertEqual(len(self.hosts.filter('host')), 1)
                        this.assertEqual(len(self.hosts.filter('extra')), 3)
                        this.assertEqual(set(self.hosts.roles), set(['host', 'extra']))
                        counter[0] += 1

        env = Env(A())
        env.B.action()
        self.assertEqual(counter[0], 6)

    def test_nesting_normal_node_in_simple_node(self):
        # It is possible to nest multiple sequences of Node-SimpleNode.Array
        # inside each other. This behaves like a multi-dimensional array.
        this = self

        class A(Node):
            class Hosts:
                role1 = LocalHost1, LocalHost2, LocalHost3
                role2 = LocalHost2, LocalHost4, LocalHost5

            @map_roles('role1', extra='role2')
            class B(SimpleNode.Array):
                class C(SimpleNode):
                    @map_roles(role='extra')
                    class D(Node):
                        @map_roles('role')
                        class E(SimpleNode.Array):
                            def action(self):
                                pass

        env = Env(A())
        self.assertEqual(env.B.C[0]._isolated, True)
        self.assertEqual(env.B.C[0].parent._isolated, True)

        env.B[0].C
        env.B[0].C.D.E
        env.B[0].C.D.E[0]
        env.B[0].C.D.E[0]

    def test_invalid_nesting(self):
        """
        TODO:
            - Test everything in host_container.
            - Take $TERM from the client terminal. (In case of a fuse-filesystem-system, we can
              easily have another $TERM for each connection.)
            - test 'hosts' vs. 'host'
            - test whether Node.node_group is a Group class.
            - test exceptions in action.
            - test mapping invalid roles to SimpleNode

            We need to have a HostContext, where we save the cd/env/... from a host.
            and a Host should become a singleton instance again.
        """

if __name__ == '__main__':
    unittest.main()
