from deployer.service import Service
from deployer.host import Host


__doc__ = """

*** Utilities for host based authentication. ***

Used by deployment of:
- postgres
- nginx

"""


class AccessFor(Service):
    allow_everyone = False
    allow_localhost = True

    @property
    def allow_tuples(self):
        return [ ]


class AllowEveryone(AccessFor):
    allow_everyone = True


class DenyEveryone(AccessFor):
    allow_everyone = False
    allow_localhost = False


class SimpleAccessList(AccessFor):
    """
    Helper class for generation of host based authentication lists.
    e.g. for Nginx or Postgres pg_hba.
    """
    allow_everyone = False

    # Include can be any other AccessFor class, or pointer to one.
    include = None

    @property
    def allow_addresses(self):
        """
        List of domain names or IPs which can access this service.
        You can use ('ip address', 'description') tuples.
        """
        return [ ]

    @property
    def allow_roles(self):
        return [ ]

    @property
    def allow_hosts(self):
        """
        Return a list of hosts instances. For instance, by filtering the
        self.hosts object.
        """
        return self.hosts.filter(self.allow_roles)

    @property
    def allow_tuples(self):
        items = []

        # Localhost
        if self.allow_localhost:
            items.append( ('127.0.0.1/24', 'Localhost') )

        # Addresses
        def add(o):
            # Extract (address, description) tuples?
            if isinstance(o, tuple):
                items.append(o)
            elif isinstance(o, basestring):
                items.append( (o, '(without name)') )

        map(add, self.allow_addresses)

        # Hosts
        for h in self.allow_hosts:
            items.append( ('%s/32' % h.get_ip_address(), '%s (Internal IP Address)' % h.slug) )
            # items.append( (h.address, '%s (Addresing)' % h.slug) )

            #    NOTE: apparently, Nginx does not support "allow DNS", only
            #          "allow IP".
            #

        # When an include is given, also take the include
        if self.include:
            map(items.append, self.include.allow_tuples)

        return sorted(items)
