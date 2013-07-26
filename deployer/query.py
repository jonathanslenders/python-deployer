import inspect

# Domain specific language for querying in a deploy tree.

__doc__ = \
"""
Queries provide syntactic sugar for expressions inside nodes.

::

    class MyNode(Node):
        do_something = True

        class MyChildNode(Node):
            do_something = Q.parent.do_something

            def setup(self):
                if self.do_something:
                    ...
                    pass
"""


__all__ = ('Q', )


class Query(object):
    """
    Node Query object.
    """
    def __init__(self):
        c = inspect.currentframe()

        # Track the file and line number where this expression was created.
        self._filename = self._line = None
        for f in inspect.getouterframes(inspect.currentframe()):
            self._filename = f[1]
            self._line = f[2]

            if not 'deployer/query.py' in self._filename:
                break

    def _execute_query(self, instance):
        return NotImplementedError

    def __getattr__(self, attrname):
        """
        Attribute lookup.
        """
        return AttrGetter(self, attrname)

    def __call__(self, *args, **kwargs):
        """
        Handle .method(param)
        """
        return Call(self, args, kwargs)

    def __getitem__(self, key):
        """
        Handle self[key]
        """
        return ItemGetter(self, key)

    @property
    def parent(self):
        """
        Go to the current parent of this node.
        """
        return Parent(self)

    # Operator overloads
    def __mod__(self, other):
        return Operator(self, other, lambda a, b: a % b, '%')

    def __add__(self, other):
        return Operator(self, other, lambda a, b: a + b, '+')

    def __sub__(self, other):
        return Operator(self, other, lambda a, b: a - b, '-')

    def __mul__(self, other):
        return Operator(self, other, lambda a, b: a * b, '*')

    def __div__(self, other):
        return Operator(self, other, lambda a, b: a / b, '/')

    # Reverse operator overloads
    def __radd__(self, other):
        return Operator(other, self, lambda a, b: a + b, '+')

    def __rsub__(self, other):
        return Operator(other, self, lambda a, b: a - b, '-')

    def __rmul__(self, other):
        return Operator(other, self, lambda a, b: a * b, '*')

    def __rdiv__(self, other):
        return Operator(other, self, lambda a, b: a / b, '/')

    def __repr__(self):
        return 'Query(...)'

    # You cannot override and, or and not:
    # Instead, we override the bitwise operators
    # http://stackoverflow.com/questions/471546/any-way-to-override-the-and-operator-in-python

    def __and__(self, other):
        return Operator(self, other, lambda a, b: a and b, '&')

    def __or__(self, other):
        return Operator(self, other, lambda a, b: a or b, '|')

    def __invert__(self):
        return Invert(self)


class QueryResult(object):
    """
    Wrap the output of a query along with all the subqueries
    that were done during it's evaluation.
    (Mainly for reflexion on queries, and its understanding for te end-user.)
    """
    def __init__(self, query, result, subqueries=None):
        self.query = query
        self.result = result
        self.subqueries = subqueries or [] # List of subquery results

    def __repr__(self):
        return 'QueryResult(query=%r, result=%r)' % (self.query, self.result)

    def walk_through_subqueries(self):
        """
        Yield all queries, and their result
        """
        for s in self.subqueries:
            for r in s.walk_through_subqueries():
                yield r
        yield self.query, self.result


def _resolve(o):
    """
    Make sure that this object becomes a Query object.
    In case of a tuple/list, create a QueryTuple/List,
    otherwise, return a Static
    """
    if isinstance(o, Query):
        return o

    elif isinstance(o, tuple):
        return Tuple(o)

    elif isinstance(o, list):
        return List(o)

    elif isinstance(o, dict):
        return Dict(o)

    else:
        return Static(o)


class Tuple(Query):
    # Resolving tuples is very useful for:
    #     Q("%s/%s") % (Q.var1, Q.var2)
    cls = tuple

    def __init__(self, items):
        self.items = [ _resolve(i) for i in items ]

    def _execute_query(self, instance):
        parts = [ i._execute_query(instance) for i in self.items ]
        return QueryResult(self,
                self.cls(i.result for i in parts),
                parts)

class List(Tuple):
    cls = list

class Dict(Query):
    # Both the keys and the values will be resolved
    #     Q("%(magic)s") % {Q.key: Q.value} is possible
    cls = dict

    def __init__(self, items):
        self.items = { _resolve(k): _resolve(v) for k, v in items.iteritems() }

    def _execute_query(self, instance):
        parts = { k._execute_query(instance): v._execute_query(instance) for k, v in self.items.iteritems() }
        return QueryResult(self,
                self.cls([(k.result, v.result) for k, v in parts.iteritems()]),
                parts)


class Invert(Query):
    """
    Implementation of the invert operator
    """
    def __init__(self, subquery):
        self.subquery = subquery

    def _execute_query(self, instance):
        part = self.subquery._execute_query(instance)
        return QueryResult(self, not part.result, [ part ] )

    def __repr__(self):
        return u'~ %r' % self.subquery


class Operator(Query):
    """
    Query which wraps two other query objects and an operator in between.
    """
    def __init__(self, part1, part2, operator, operator_str):
        Query.__init__(self)
        self.part1 = _resolve(part1)
        self.part2 = _resolve(part2)
        self.operator = operator
        self.operator_str = operator_str

    def _execute_query(self, instance):
        part1 = self.part1._execute_query(instance)
        part2 = self.part2._execute_query(instance)

        return QueryResult(self,
                self.operator(part1.result, part2.result),
                [ part1, part2 ])

    def __repr__(self):
        return u'%r %s %r' % (self.part1, self.operator_str, self.part2)


class ItemGetter(Query):
    """
    Query which takes an item of the result from another query.
    """
    def __init__(self, subquery, key):
        Query.__init__(self)
        self.subquery = subquery
        self.key = _resolve(key)

    def _execute_query(self, instance):
        # The index object can be a query itself. e.g. Q.var[Q.var2]
        part = self.subquery._execute_query(instance)
        key = self.key._execute_query(instance)
        return QueryResult(self,
            part.result[key.result], [part, key])

    def __repr__(self):
        return '%r[%r]' % (self.subquery, self.key)


class Static(Query):
    """
    Query which represents just a static value.
    """
    def __init__(self, value):
        Query.__init__(self)
        self.value = value

    def _execute_query(self, instance):
        return QueryResult(self, self.value, [])

    def __repr__(self):
        # NOTE: we just return `value` instead of `Q(value)`.
        # otherwise, most of the repr calls return too much garbage,
        # most of the time, not what the user entered.
        # e.g: Q.a['value'] is automatically transformed in Q.a[Q('value')]
        return repr(self.value)


class AttrGetter(Query):
    """
    Query which takes an attribute of the result from another query.
    """
    def __init__(self, subquery, attrname):
        Query.__init__(self)
        self.subquery = subquery
        self.attrname = attrname

    def _execute_query(self, instance):
        part = self.subquery._execute_query(instance)
        return QueryResult(self,
            getattr(part.result, self.attrname), [ part ])

    def __repr__(self):
        return '%r.%s' % (self.subquery, self.attrname)


class Call(Query):
    """
    Any callable in a query.
    The parameters can be queris itself.
    """
    def __init__(self, subquery, args, kwargs):
        Query.__init__(self)
        self.subquery = subquery
        self.args = [ _resolve(a) for a in args ]
        self.kwargs = { k:_resolve(v) for k,v in kwargs.items() }

    def _execute_query(self, instance):
        part = self.subquery._execute_query(instance)
        args_results = [ a._execute_query(instance) for a in self.args ]
        kwargs_results = { k:v._execute_query(instance) for k,v in self.kwargs }

        return QueryResult(self,
                        part.result(
                                * [a.result for a in args_results],
                                **{ k:v.result for k,v in kwargs_results.items() }),
                        [ part ] + args_results + kwargs_results.values())

    def __repr__(self):
        return '%r(%s)' % (self.subquery,
                    ', '.join(map(repr, self.args) + ['%s=%r' % (k,v) for k,v in self.kwargs.items()] ))


class Parent(Query):
    """
    Query which would go to the parent of the result of another query.
    `parent('parent_name')` would go up through all the parents looking for that name.
    """
    def __init__(self, subquery):
        Query.__init__(self)
        self.subquery = subquery

    def __call__(self, parent_name):
        """
        Handle .parent(parent_name)
        """
        return FindParentByName(self.subquery, parent_name)

    def _execute_query(self, instance):
        part = self.subquery._execute_query(instance)
        return QueryResult(self, part.result.parent, [part])

    def __repr__(self):
        return '%r.parent' % self.subquery


class FindParentByName(Query):
    """
    Query which traverses the nodes in the tree, and searches for a parent having the given name.

    e.g.:

    class node(Node):
        some_property = Q('NameOfParent').property_of_that_parent
    """
    def __init__(self, subquery, parent_name):
        Query.__init__(self)
        self.subquery = subquery
        self.parent_name = parent_name

    def _execute_query(self, instance):
        part = self.subquery._execute_query(instance)

        def p(i):
            if self.parent_name in [ b.__name__ for b in inspect.getmro(i._node.__class__) ]:
                return i
            else:
                if not i.parent:
                    raise Exception('Class %s has no parent (while accessing %s from %s)' %
                                (i, self.parent_name, instance))

                return p(i.parent)

        return QueryResult(self, p(part.result), [part])

    def __repr__(self):
        return '%r.parent(%r)' % (self.subquery, self.parent_name)


class Identity(Query):
    """
    Helper for the Q object below.
    """
    def _execute_query(self, instance):
        # Return idenity func
        return QueryResult(self, instance, [])


class q(Identity):
    """
    Node Query object.
    """
    def __call__(self, string):
        """
        Allow static values, but also lists etc. to resolve further.

        Q('str') -> 'str'
        Q((Q('abc-%s') % Q.foo)) -> 'abc-bar'
        """
        return _resolve(string)

    def __repr__(self):
        return 'Q'

Q = q()
