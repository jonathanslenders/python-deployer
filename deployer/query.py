import inspect

"""
The Query object is technically a Python class descriptor. It exposes an easy
to read syntax for a service property to point to another Service's class
property.

e.g.

class MyService(Service):
    something = True

    class MySubService(Service):
        some_property = Q.parent('MyService').something
        some_service = Q.parent('MyService').SomeOtherService

    class SomeOtherService(Service):
        pass
"""


__all__ = ('Q', )


class Query(object):
    """
    Service Query object.
    """
    def __init__(self):
        pass

    @property
    def _query(self):
        return NotImplementedError

    def __getattr__(self, attrname):
        """
        Attribute lookup.
        """
        return attrgetter(self, attrname)

    def __call__(self, *args, **kwargs):
        """
        Handle .method(param)
        """
        return call(self, args, kwargs)

    def __getitem__(self, key):
        """
        Handle self[key]
        """
        return itemgetter(self, key)

    @property
    def parent(self):
        """
        Go the to current parent of this service.
        """
        return parent(self)

    def __mod__(self, other):
        """
        Module operator between two Q objects:

        class service(Service):
            my_property = Q('Some string with %s placeholder') % Q.parent.property_to_be_inserted
        """
        return operator(self, other, lambda a, b: a % b, '%')

    def __add__(self, other):
        """
        Plus operator between two Q objects.

        class service(Service):
            my_property = Q(20) % Q.parent.add_this_property
        """
        return operator(self, other, lambda a, b: a+b, '+')

    def __repr__(self):
        return '<Query: %s>' % self.__str__()

    def __str__(self):
        return 'Q'

    # You cannot override and, or and not:
    # http://stackoverflow.com/questions/471546/any-way-to-override-the-and-operator-in-python

    #def __and__(self, other):
    #    return operator(self, other, lambda a, b: a and b)

    #def __or__(self, other):
    #    return operator(self, other, lambda a, b: a or b)

    #def __not__(self):
    #    return operator(self, None, lambda a, b: not a)

def _resolve(query_object, instance):
    """
    When the parameter is a query object, resolve the query.
    But when it's a list or tuple, recursively do the same.
    """
    if isinstance(query_object, Query):
        return query_object._query(instance)

    elif isinstance(query_object, tuple):
        # Recursively resolving the tuple content is very useful for:
        #     Q("%s/%s") % (Q.var1, Q.var2)
        return tuple(_resolve(p, instance) for p in query_object)

    elif isinstance(query_object, list):
        return list(_resolve(p, instance) for p in query_object)

    else:
        return query_object


class operator(Query):
    """
    Query which wraps two other query objects and an operator in between.
    """
    def __init__(self, part1, part2, operator, operator_str):
        Query.__init__(self)
        self.part1 = part1
        self.part2 = part2
        self.operator = operator
        self.operator_str = operator_str

    @property
    def _query(self):
        def result(instance):
            return self.operator(_resolve(self.part1, instance), _resolve(self.part2, instance))
        return result

    def __str__(self):
        return u'%s %s %s' % (str(self.part1), self.operator_str, str(self.part2))


class itemgetter(Query):
    """
    Query which takes an item of the result from another query.
    """
    def __init__(self, query_before, key):
        Query.__init__(self)
        self.query_before = query_before
        self.key = key

    @property
    def _query(self):
        # The index object can be a query itself. e.g. Q.var[Q.var2]
        return lambda instance: self.query_before._query(instance)[_resolve(self.key, instance)]

    def __str__(self):
        return '%s[%s]' % (str(self.query_before), self.key)


class static(Query):
    """
    Query which represents just a static value.
    """
    def __init__(self, value):
        self.value = value

    @property
    def _query(self):
        # Return idenity func
        return lambda instance: self.value

    def __str__(self):
        return '"%s"' % self.value


class attrgetter(Query):
    """
    Query which takes an attribute of the result from another query.
    """
    def __init__(self, query_before, attrname):
        self.query_before = query_before
        self.attrname = attrname

    @property
    def _query(self):
        def q(instance):
            return getattr(self.query_before._query(instance), self.attrname)
        return q

    def __str__(self):
        return '%s.%s' % (str(self.query_before), self.attrname)


class call(Query):
    """
    Query which would call the result of another query.
    """
    def __init__(self, query_before, args, kwargs):
        self.query_before = query_before
        self.args = args
        self.kwargs = kwargs

    @property
    def _query(self):
        return lambda instance: self.query_before._query(instance)(* self.args, ** self.kwargs)

    def __str__(self):
        return '%s(%s)' % (str(self.query_before),
                        ','.join(map(str, self.args) + ['%s=%s' % (k,str(v)) for k,v in self.kwargs.items()] ))


class parent(Query):
    """
    Query which would go to the parent of the result of another query.
    `parent('parent_name')` would go up through all the parents looking for that name.
    """
    def __init__(self, query_before):
        self.query_before = query_before

    def __call__(self, parent_name):
        """
        Handle .parent(parent_name)
        """
        return find_parent_by_name(self.query_before, parent_name)

    @property
    def _query(self):
        return lambda instance: self.query_before._query(instance).parent

    def __str__(self):
        return u'%s.parent' % str(self.query_before)


class find_parent_by_name(Query):
    """
    Query which traverses the services tree, and searches for a parent having the given name.

    e.g.:

    class service(Service):
        some_property = Q('NameOfParent').property_of_that_parent
    """
    def __init__(self, query_before, parent_name):
        self.query_before = query_before
        self.parent_name = parent_name

    @property
    def _query(self):
        def parentfinder(instance):
            def p(i):
                if self.parent_name in [ b.__name__ for b in inspect.getmro(i._service.__class__) ]:
                    return i
                else:
                    if not i.parent:
                        raise Exception('Class %s has no parent (while accessing %s from %s)' % (i, self.parent_name, instance))

                    return p(i.parent)

            return p(self.query_before._query(instance))

        return parentfinder

    def __str__(self):
        return '%s.parent("%s")' % (str(self.query_before), self.parent_name)

class identity(Query):
    """
    Helper for the Q object below.
    """
    @property
    def _query(self):
        # Return idenity func
        return lambda instance: instance


class q(identity):
    """
    Service Query object.
    """
    def __call__(self, string):
        """
        Handle Q(some_value) as a static value.
        """
        return static(string)

Q = q()
