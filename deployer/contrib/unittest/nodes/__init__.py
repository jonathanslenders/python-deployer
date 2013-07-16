
from deployer.node import Node
from deployer.query import Q

from termcolor import colored


def test(description, expected, func, should_fail=False):
    """
    Execute test
    """
    print description,

    try:
        value = func()
        succeeded = not should_fail
    except:
        value = None
        succeeded = should_fail

    if succeeded and value == expected:
        print colored(' [OK]', 'green')
    else:
        print colored(' [FAILED]', 'failed')


class UnitTest(Node):
    def fail_with_error(self):
        """
        This is an action which failes with an error.
        A nice traceback should be shown in the shell.
        (If this was called from the shell.)
        """
        self._error_func()

    def _error_func(self):
        self._error_func2()

    def _error_func2(self):
        raise Exception('Something went wrong (dummy exception)')

    def eternal_recursion(self):
        self.eternal_recursion()

    def false_status_code_exception(self):
        self.hosts.run('/bin/false')

    #
    # Q-object tests
    #

    var1 = 'a'
    var2 = 'b'
    var3 = 55
    var4 = 22
    var5 = 2
    var_list = [1,2,3,4]
    #q_addition = Q.var3 + Q.var4
    #q_substraction = Q.var3 - Q.var4
    q_modulo = Q('%s/%s') % (Q.var1, Q.var2)
    q_index = Q.var_list[Q.var5]
    q_invalid = Q.some.invalid.query

    def test_q_object(self):
        test('Q-object: variable retreival', 'a', lambda: self.var1)
        #test('Q-object: addition', 77, lambda: self.q_addition)
        #test('Q-object: substraction', 33, lambda: self.q_substraction)
        test('Q-object: module operator', 'a/b', lambda: self.q_modulo)
        test('Q-object: index operator (Q.var[Q.var2])', 3, lambda: self.q_index)
        test('Q-object exception', None, lambda: self.q_invalid, should_fail=True)
