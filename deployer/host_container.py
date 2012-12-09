from contextlib import nested
from deployer.host import Host
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
    """
    def __init__(self, hosts, pty=None, logger=None, is_sandbox=False):
        # the hosts parameter is a dictionary, mapping roles to <Host> instances, or lists
        # of <Host>-instances.
        # e.g. hosts = { 'www': [ <host1>, <host2> ], 'queue': <host3> }
        self._hosts = hosts
        self._logger = logger
        self._pty = pty
        self._is_sandbox = is_sandbox

        # Make set of all hosts.
        all_hosts = set()
        for h in hosts.values():
            if isinstance(h, Host):
                all_hosts.add(h)
            else:
                for i in h:
                    all_hosts.add(i)

        self._all = list(all_hosts)

        # Validate hosts. No two host with the same slug can occur in a
        # container.
        slugs = set()
        for h in self._all:
            if h.slug in slugs:
                raise Exception('Duplicate host slug %s found.' % h.slug)
            else:
                slugs.add(h.slug)

    def __repr__(self):
        return ('<%s\n' % self.__class__.__name__ +
                ''.join('   %s: [%s]\n' % (r, ','.join(h.slug for h in self.filter(r))) for r in self.roles) +
                '>')

    def _new(self, hosts):
        return HostsContainer(hosts, self._pty, self._logger, self._is_sandbox)

    def _new_1(self, host):
        return HostContainer({ 'host': host }, self._pty, self._logger, self._is_sandbox)

    def __len__(self):
        return len(self._all)

    def __nonzero__(self):
        return len(self._all) > 0

    def count(self):
        return len(self._all)

    @property
    def roles(self):
        return self._hosts.keys()

    def contains(self, host):
        """
        Return true when this host appears in this host container.
        """
        for h in self._all:
            #if h in host._all:
            if any(h.slug == host.slug for h in host._all):
                return True
        return False

    def get_from_slug(self, host_slug):
        for h in self._all:
            if h.slug == host_slug:
                return self._new_1(h)
        raise AttributeError

    def contains_host_with_slug(self, host_slug):
        return any(h.slug == host_slug for h in self._all)

    def clone(self):
        return self._new(self._hosts)

    def filter(self, *roles):
        """
        Usage:
            hosts.filter('role1', 'role2')
            or
            hosts.filter( ['role1', 'role2' ]) # TODO: deprecate
            or
            host.filter('role1', MyHostClass) # This means: take 'role1' from this container, but add an instance of this class

        """
        if len(roles) == 1 and any(isinstance(roles[0], t) for t in (tuple, list)): # TODO: deprecate this line.
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

    def isolate(self, role, host_slug):
        """
        Make sure that for the given role, only a host with `host_slug` will
        stay over.
        """
        result = { role: self.filter(role).get_from_slug(host_slug)._all }

        for r, hosts in self._hosts.items():
            if r != role:
                result[r] = hosts #[:]

        return self._new(result)

    def iterate_isolations(self, role):
        """
        Yield a HostsContainer for every isolation in this role.
        """
        for h in self.filter(role):
            yield h, self.isolate(role, h.slug)

    def __getitem__(self, index):
        return self._new_1(self._all[index])

    def __iter__(self):
        for h in self._all:
            yield self._new_1(h)

    def _sandbox_if_required(self, host):
        return host.sandbox() if self._is_sandbox else nested()

    @wraps(Host.run)
    def run(self, *args, **kwargs):
        """
        Call 'run' with this parameters on every host.
        Return an array of all the results.
        """
        kwargs['logger'] = self._logger

        # When addressing multiple hosts and auxiliary ptys are available,
        # do a parallel run.
        if len(self._all) > 1 and self._pty.auxiliary_ptys_are_available:
            # First create a list of callables
            def closure(host):
                def call(pty):
                    with self._sandbox_if_required(host):
                        return host.run(pty, *args, **kwargs)
                return call

            callables = [ closure(h.clone()) for h in self._all ]

            # Run in auxiliary ptys, wait for them all to finish,
            # and return result.
            print 'Forking to %i pseudo terminals...' % len(callables)

            # Wait for the forks to finish
            fork_result = self._pty.run_in_auxiliary_ptys(callables)
            fork_result.join()
            result = fork_result.result

            # Return result.
            print ''.join(result) # (Print it once more in this terminal, not really sure whether we should do that.)
            return result

        # Otherwise, run all serially.
        else:
            output = []
            for h in self._all:
                with self._sandbox_if_required(h):
                    output.append(h.run(self._pty, *args, **kwargs))

            return output

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

    @wraps(Host.prefix)
    def prefix(self, *args, **kwargs):
        """
        Call 'prefix' with this parameters on every host.
        """
        return nested(* [ h.prefix(*args, **kwargs) for h in self._all ])

    @wraps(Host.cd)
    def cd(self, *args, **kwargs):
        """
        Call 'cd' with this parameters on every host.
        """
        return nested(* [ h.cd(*args, **kwargs) for h in self._all ])

    @wraps(Host.env)
    def env(self, *args, **kwargs):
        """
        Call 'env' with this parameters on every host.
        """
        return nested(* [ h.env(*args, **kwargs) for h in self._all ])


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
            kwargs['logger'] = self._logger # TODO: maybe also pass logger through with-context

            with self._sandbox_if_required(self._host):
                return self._host.get(*args, **kwargs)
        else:
            raise AttributeError

    @wraps(Host.put)
    def put(self, *args,**kwargs):
        if len(self) == 1:
            kwargs['logger'] = self._logger
            with self._sandbox_if_required(self._host):
                return self._host.put(*args, **kwargs)
        else:
            raise AttributeError

    @wraps(Host.open)
    def open(self, *args,**kwargs):
        if len(self) == 1:
            kwargs['logger'] = self._logger

            with self._sandbox_if_required(self._host):
                return self._host.open(*args, **kwargs)
        else:
            raise AttributeError

    @wraps(HostsContainer.run)
    def run(self, *a, **kw):
        return HostsContainer.run(self, *a, **kw)[0]

    @wraps(HostsContainer.sudo)
    def sudo(self, *a, **kw):
        return HostsContainer.sudo(self, *a, **kw)[0]

    def start_interactive_shell(self, command=None, initial_input=None):
        if not self._is_sandbox:
            return self._host.start_interactive_shell(self._pty, command=command, initial_input=initial_input)
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
