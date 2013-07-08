The query object
================

Queries provide syntactic sugar for expressions inside nodes.
For instance:

::

    class MyNode(Node):
        do_something = True

        class MyChildNode(Node):
            do_something = Q.parent.do_something

            def setup(self):
                if self.do_something:
                    ...
                    pass


Technically, such a Query object uses the descriptor protocol.  This way, it
acts like any python ``property``, and is completely transparent.


More examples
-------------

A query can address the attribute of an inner node.  When the property
``attribute_of_a`` in the example below is retrieved, the query executes and
accesses the inner node ``A`` in the background.

::

    class Root(Node):
        class A(Node):
            attribute = 'value'

        attribute_of_a = Q.A.attribute

        def action(self):
            if self.attribute_of_a == 'value':
                do_something(...)

A query can also call a function. The method ``get_url`` is called in the background.

::

    class Root(Node):
        class A(Node):
            def get_url(self, domain):
                return 'http://%s' % domain

        url_of_a = Q.A.get_url('example.com')

        def print_url(self):
            print self.url_of_a

.. note:: Please make sure that a query can execute without side effects. This
         means, that a query should never execute a command that changes
         something on a host. Consider it read-only, like the getter of a
         property.

         (This is mainly a convension, but could result in unexpected results
         otherwise.)

A query can even do complex calculations:

::

    class Root(Node):
        class A(Node):
            length = 4
            width = 5

        # Multiply
        size = Q.A.length * Q.A.width

        # Operator priority
        size_2 = (Q.A.length + 1) * Q.A.width

        # String interpolation
        size_str = Q('The size is %s x %s') % (Q.A.height, Q.A.width)


.. note:: Python does not support overloading of the ``and``, ``or`` and
          ``not`` operators. You should use the bitwise equivalents ``&``, ``|``
          and ``~`` instead.

Reference
---------

TODO: implemented operators

TODO: implemented special methods: __getitem__, 
