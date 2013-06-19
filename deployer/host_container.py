from contextlib import nested
from deployer.host import Host, HostContext
from deployer.utils import isclass
from functools import wraps


__all__ = ('HostContainer', 'HostsContainer', )


class HostsContainer(object):
    """
    Facade to the host instances.
    if you have a role, name 'www' inside the service webserver, you can do:

    - webserver.hosts.run(...)
    - webserver.hosts.www.run(...)
    - webserver.hosts[0].run(...)
    - webserver.hosts.www[0].run(...)
    - webserver.hosts.filter('www')[0].run(...)

    The host container also keeps track of HostStatus. So, if we fork a new
    thread, and the HostStatus object gets modified in either thread. Clone
    this HostsContainer first.
    """
    def __init__(self, hosts, pty=None, logger=None, is_sandbox=False, host_contexts=None):
        # the hosts parameter is a dictionary, mapping roles to <Host> instances, or lists
        # of <Host>-instances.
        # e.g. hosts = { 'www': [ <host1>, <host2> ], 'queue': <host3> }
        self._hosts = hosts
        self._logger = logger
        self._pty = pty
        self._sandbox = is_sandbox

        # Make set of all hosts.
        all_hosts = set()
        for h in hosts.values():
            if isclass(h) and issubclass(h, Host):
                all_hosts.add(h)
            else:
                for i in h:
                    all_hosts.add(i)

        self._all = list(all_hosts) # TODO: Why is this a set???

        # Validate hosts. No two host with the same slug can occur in a
        # container.
        slugs = set()
        for h in self._all:
            if h.slug in slugs:
                raise Exception('Duplicate host slug %s found.' % h.slug)
            else:
                slugs.add(h.slug)

        # Host statuses ( { Host class : HostStatus } )
        if host_contexts:
            self._host_contexts = { h: host_contexts.get(h, HostContext()) for h in self._all }
        else:
            self._host_contexts = { h: HostContext() for h in self._all }

    @classmethod
    def from_definition(cls, hosts_class, **kw):
        """
        Create a host container from a Hosts class.
        """
        hosts = { }
        for k in dir(hosts_class):
            v = getattr(hosts_class, k)

            if isinstance(v, HostsContainer):
                hosts[k] = v._all
            elif isclass(v) and issubclass(v, Host):
                hosts[k] = [ v ]
            elif isinstance(v, (list, tuple)):
                hosts[k] = v
            elif not k.startswith('_'):
                raise TypeError('Invalid attribute in Hosts: %r=%r' % (k, v))

        return cls(hosts, **kw)

    def __repr__(self):
        return ('<%s\n' % self.__class__.__name__ +
                ''.join('   %s: [%s]\n' % (r, ','.join(h.slug for h in self.filter(r))) for r in self.roles) +
                '>')

    def __eq__(self, other):
        """
        Return True when the roles/hosts are the same.
        """
        if self.roles != other.roles:
            return False

        for r in self.roles:
            if set(self.filter(r)._all) != set(other.filter(r)._all):
                return False

        return True

    def _new(self, hosts):
        return HostsContainer(hosts, self._pty, self._logger, self._sandbox,
                        host_contexts=self._host_contexts)

    def _new_1(self, host):
        return HostContainer({ 'host': [host] }, self._pty, self._logger, self._sandbox,
                        host_contexts=self._host_contexts)

    def __len__(self):
        return len(self._all)

    def __nonzero__(self):
        return len(self._all) > 0

    def count(self): # TODO: depricate count --> we have len()
        return len(self._all)

    @property
    def roles(self):
        return sorted(self._hosts.keys())

    def __contains__(self, host):
        """
        Return true when this host appears in this host container.
        """
        return host in self._all

    def get_from_slug(self, host_slug):
        for h in self._all:
            if h.slug == host_slug:
                return self._new_1(h)
        raise AttributeError

    def contains_host_with_slug(self, host_slug):
        return any(h.slug == host_slug for h in self._all)

    def clone(self):
        return self._new(self._hosts) # TODO: clone HostContext recursively!!

    def filter(self, *roles):
        """
        Usage:
            hosts.filter('role1', 'role2')
            or
            hosts.filter( ['role1', 'role2' ]) # TODO: deprecate
            or
            host.filter('role1', MyHostClass) # This means: take 'role1' from this container, but add an instance of this class

        """
        if len(roles) == 1 and any(isinstance(roles[0], t) for t in (tuple, list)):
            roles = roles[0]

        return self._new(_filter_hosts(self._hosts, roles))

    def get(self, *roles):
        """
        Similar to filter(), but returns exactly one host instead of a list.
        """
        result = self.filter(*roles)
        if len(result) == 1:
            return self._new_1(result._all[0])
        else:
            raise AttributeError

    def __getitem__(self, index):
        return self._new_1(self._all[index])

    def __iter__(self):
        for h in self._all:
            yield self._new_1(h)

    @wraps(Host.run)
    def run(self, *a, **kw):
        """
        Call 'run' with this parameters on every host.
        Return an array of all the results.
        """
        # First create a list of callables
        def closure(host):
            def call(pty):
                kw2 = dict(**kw)
                kw2['sandbox'] = self._sandbox
                kw2['context'] = self._host_contexts[host]
                kw2['logger'] = self._logger
                return host.get_instance().run(pty, *a, **kw2)
            return call

        callables = map(closure, self._all)

        # When addressing multiple hosts and auxiliary ptys are available,
        # do a parallel run.
        if len(callables) > 1 and self._pty.auxiliary_ptys_are_available:
            # Run in auxiliary ptys, wait for them all to finish,
            # and return result.
            print 'Forking to %i pseudo terminals...' % len(callables)

            # Wait for the forks to finish
            fork_result = self._pty.run_in_auxiliary_ptys(callables)
            fork_result.join()
            result = fork_result.result

            # Return result.
            print ''.join(result) # (Print it once more in the main terminal, not really sure whether we should do that.)
            return result

        # Otherwise, run all serially.
        else:
            return [ c(self._pty) for c in callables ]

    @wraps(Host.sudo)
    def sudo(self, *args, **kwargs):
        """
        Call 'sudo' with this parameters on every host.
        """
        kwargs['use_sudo'] = True
        return HostsContainer.run(self, *args, **kwargs)
                    # NOTE: here we use HostsContainer instead of self, to be
                    #       sure that we don't call te overriden method in
                    #       HostContainer.

    @wraps(HostContext.prefix)
    def prefix(self, *a, **kw):
        """
        Call 'prefix' with this parameters on every host.
        """
        return nested(* [ s.prefix(*a, **kw) for s in self._host_contexts ])

    @wraps(HostContext.cd)
    def cd(self, *a, **kw):
        """
        Call 'cd' with this parameters on every host.
        """
        return nested(* [ s.cd(*a, **kw) for s in self._host_contexts ])

    @wraps(HostContext.env)
    def env(self, *a, **kw):
        """
        Call 'env' with this parameters on every host.
        """
        return nested(* [ s.env(*a, **kw) for s in self._host_contexts.values() ])


class HostContainer(HostsContainer):
    """
    Similar to hostsContainer, but wraps only around exactly one host.
    """
    @property
    def _host(self):
        """
        This host container has only one host.
        """
        return self._all[0]

    @property
    def slug(self):
        return self._host.slug

    @wraps(Host.get)
    def get(self, *args,**kwargs):
        if len(self) == 1:
            kwargs['logger'] = self._logger
            kwargs['sandbox'] = self._sandbox

            return self._host.get_instance().get(*args, **kwargs)
        else:
            raise AttributeError

    @wraps(Host.put)
    def put(self, *args,**kwargs):
        if len(self) == 1:
            kwargs['logger'] = self._logger
            kwargs['sandbox'] = self._sandbox

            return self._host.get_instance().put(*args, **kwargs)
        else:
            raise AttributeError

    @wraps(Host.open)
    def open(self, *args,**kwargs):
        if len(self) == 1:
            kwargs['logger'] = self._logger
            kwargs['sandbox'] = self._sandbox

            return self._host.get_instance().open(*args, **kwargs)
        else:
            raise AttributeError

    @wraps(HostsContainer.run)
    def run(self, *a, **kw):
        return HostsContainer.run(self, *a, **kw)[0]

    @wraps(HostsContainer.sudo)
    def sudo(self, *a, **kw):
        return HostsContainer.sudo(self, *a, **kw)[0]

    def start_interactive_shell(self, command=None, initial_input=None):
        if not self._sandbox:
            return self._host.get_instance().start_interactive_shell(self._pty, command=command, initial_input=initial_input)
        else:
            print 'Interactive shell is not available in sandbox mode.'

    def __getattr__(self, name):
        """
        Proxy to the Host object. Following commands can be
        accessed when this hostcontainer contains exactly one host.
        """
        return getattr(self._host, name)


def _filter_hosts(hosts_dict, roles):
    """
    Take a hosts dictionary and return a subdictionary of the hosts matching this roles.
    When some of the roles are Host classes, initiate the host class instead.
    """
    if isinstance(roles, basestring):
        roles = [roles]

    def get(r):
        """
        When the query is a string, look it up in the dictionary,
        but when it is a host class, initiate the class instead.
        """
        if isinstance(r, basestring):
            return hosts_dict.get(r, [])
        elif isinstance(r, Host):
            return r.get_instance()
        else:
            raise Exception('Unknown host filter: %s' % r)

    return { r: get(r) for r in roles }


def _isolate_hosts(hosts_dict, role, host_slug):
    """
    Make sure that for the given role, only a host with `host_slug` will
    stay over.
    """
    result = { }
    for r, hosts in hosts_dict.items():
        if r == role:
            result[r] = [ h for h in hosts if h.slug == host_slug ]
        else:
            result[r] = hosts[:]
    return result
