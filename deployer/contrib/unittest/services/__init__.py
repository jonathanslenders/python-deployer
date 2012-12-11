
from deployer.service import Service
from deployer.query import Q


class UnitTest(Service):
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

    def query_exception(self):
        self.invalid_query

    invalid_query = Q.some.invalid.query

    def false_status_code_exception(self):
        self.hosts.run('/bin/false')


    var1 = 'a'
    var2 = 'b'
    varc = Q('%s/%s') % (Q.var1, Q.var2)

    def test_modulo_tuple(self):
        print self.varc


    var4 = [1,2,3,4]
    var5 = 2
    vard = Q.var4[Q.var5]

    def test_query_in_itemgetter(self):
        return self.vard
