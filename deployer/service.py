from deployer.console import input
from deployer.host import Host
from deployer.host_container import HostsContainer, HostContainer
from deployer.service_groups import Group
from deployer.loggers import DummyLoggerInterface
from deployer.loggers.trace import TraceLogger
from deployer.pty import DummyPty, Pty
from deployer.query import Query
from deployer.utils import capture

from functools import wraps
from inspect import isfunction
import inspect
import traceback
import types
import datetime

__all__ = ('Service', 'map_roles', 'supress_action_result', 'default_action', 'required_property', 'alias', )



def isclass(obj):
    """
    Helper.

    Identical to Python 2.7 's inspect.isclass.
    isclass in Python 2.6 also returns True when
    the passed object has a __bases__ attribute.
    (like in case of an instance.)
    """
    return isinstance(obj, (type, types.ClassType))




# ======================[ Role mappings ]=============================


class RoleMapping(object):
    """
    Definition/rules of how the hosts of a parent service are
    mapped to a child service.

    An instance of this class should be assigned to the Meta.role_mapping field
    of a Service class.
    """
    def apply(self, parent_service_instance):
        """
        Return a host mapping dictionary, by applying the mapping rules from
        this parent service instance.
        """
        return { } # By default, an empty mapping

    @property
    def assert_just_one_isolation(self):
        return False


class RoleMappingDecorator(object):
    """
    Role mapping decorators take a Service class definition,
    and attach a Meta.role_mapping function to a copy of the class definition.

    When the class is instantiated, the mapper function will be evaluated
    against the parent service, and the hosts subset will be passed to
    the subservice constructor.

    # If no mapping decorator was places around a class, it is equivalent to:
        @map_roles

    # If you want a service which contains isolations roles not to behave
    # like an array, but just a single instance, use `just_one'. This will
    # assert that only one host is in the isolate_role.
        @map_roles.just_one

    # You can also manually specify the mappings.
        @map_roles(role='parent_role', role2=['parent_role2', 'parent_role3'])
        @map_roles.just_one(role='parent_role', role2=['parent_role2', 'parent_role3'])

    # It is even possible to use a Host class instead of a string. In that
    # case, this class will always be included.

        @map_roles(host=MyHost)
    """
    def __init__(self, auto=True, just_one=False, mappings=None):
        self._auto = auto # Auto map roles
        self._just_one = just_one
        self._mappings = mappings or { }

    def __call__(self, *args, **kwargs):
        # Apply decorator to a service class
        if len(args) == 1 and len(kwargs) == 0:
            subservice_class = args[0]

            # Inherit original service class, but keep the original name. Add the
            # mappings in an attribute _role_mapping_func.
            if not isclass(subservice_class) or not issubclass(subservice_class, Service):
                raise Exception('Role mapping decorator incorrectly applied. %s is not a Service class' % subservice_class)

            # By using 'type', we create a copy of the service class (by
            # inheriting), in order to avoid modifications to the original.
            # (This would cause problems if other references to the class
            # definition exist elsewhere.)
            new_meta = type('Meta', (subservice_class.Meta, ), { 'role_mapping': self.create_role_mapping() })
            return type(subservice_class.__name__, (subservice_class, ), { 'Meta': new_meta })

        # Else, passing in role mappings
        elif len(args) == 0 and len(kwargs):
            return RoleMappingDecorator(auto=False, just_one=self._just_one, mappings=kwargs)

        else:
            raise Exception('Role mapping decorator incorrectly applied.')

    @property
    def just_one(self):
        return RoleMappingDecorator(auto=self._auto, just_one=True, mappings=self._mappings)

    def create_role_mapping(self):
        class role_mapping(RoleMapping):
            def apply(m, parent_service_instance):
                """
                Map roles from the parent to the sub service, using this addressing key.
                """
                result = { }

                # For every role in the mapping
                for role, filter_values in self._mappings.items():
                    # Note that filter_values, can be a list of names, but
                    # it can also contain additional Host classes.
                    result[role] = parent_service_instance.hosts.filter(filter_values)._all

                # Auto-map other roles.
                # This will map roles from the parent service to the same name
                # on the child, when they were not explicitely defined.
                if self._auto:
                    for role in parent_service_instance.Meta.roles:
                        if role not in result:
                            result[role] = parent_service_instance.hosts.filter(role)._all
                return result

            @property
            def assert_just_one_isolation(m):
                return self._just_one

        return role_mapping()

map_roles = RoleMappingDecorator()


# ======================[ Service ]=====================

class ActionDescriptor(object):
    """
    Every instancemethod in a Service will be wrapped by this descriptor.
    """
    def __init__(self, func):
        self._func = func

    def __get__(self, instance, owner):
        if instance:
            return Action(instance, self._func)
        else:
            # TODO: we should avoid this usage. e.g. in "Config.setup(self)"
            #       this causes Action to lack a service instance, and a
            #       retrieval path...

            return Action(None, self._func)
            #raise Exception("Don't retrieve action from the class object. Use instance.action")
            #return self._func


class ServiceDescriptor(object):
    """
    Every nested Service class definition in a Service will be wrapped by this descriptor. For instance:

    >> class ParentService(Service):
    >>     class ChildService(Service):
    >>         pass
    """
    def __init__(self, service_class):
        self._service_class = service_class

    def __get__(self, parent_instance, owner):
        """
        When the child service is retrieved from an instance of the parent service, an instance of the child service
        will be returned (and the hosts from the parent are mapped to the child.)

        Depending on the value of Meta.isolate_role of the child service. This will act as an array of isolated
        services (for each host), or as a single unit.
        """
        if parent_instance:
            service_hosts = HostsContainer(self._service_class.Meta.role_mapping.apply(parent_instance))

            # Consider this service instance isolated, when...
            if parent_instance._is_isolated:
                # 1. The parent is isolated, and we assert only one isolation
                # in this service. (through the role mapping)
                assert_just_one_isolation = self._service_class.Meta.role_mapping.assert_just_one_isolation

                if self._service_class.Meta.isolate_role and assert_just_one_isolation:
                    # Check again, whether there were no multiple hosts passed
                    # into this role.
                    hosts_in_isolation_role = len(service_hosts.filter(self._service_class.Meta.isolate_role))

                    if hosts_in_isolation_role == 1:
                        is_isolated = True
                    else:
                        raise Exception('%i hosts in isolation role, while using @map_roles.just_one' % hosts_in_isolation_role) # TODO: better exception

                # 2. Parent already isolated, and the current service does not have its own isolation rule.
                elif not self._service_class.Meta.isolate_role:
                    is_isolated = True
                else:
                    is_isolated = False

            # Parent not isolated, they we aren't as well.
            else:
                is_isolated = False

            # Create service instance.
            return self._service_class(service_hosts,
                            path=parent_instance._path + [parent_instance], name=self._service_class.__name__,
                            parent=parent_instance, creator_service=parent_instance, is_isolated=is_isolated)
        else:
            return self._service_class


class PropertyDescriptor(object):
    def __init__(self, attribute):
        self.attribute = attribute

    def __get__(self, instance, owner):
        if instance:
            return Action(instance, self.attribute.fget, is_property=True)
        else:
            return self.attribute


class QueryDescriptor(object):
    def __init__(self, service_name, attr_name, query):
        self.service_name = service_name
        self.attr_name = attr_name
        self.query = query

    def __get__(self, instance, owner):
        def run(i):
            """
            Wrapper for the query function which properly handles exceptions.
            """
            try:
                return self.query._query(i)
            except Exception, e:
                from deployer.exceptions import QueryException
                raise QueryException(i._service, self.attr_name, self.query, e)

        # Make sure that a nice name is passed to Action
        run.__name__ = str('query:%s' % self.query.__str__())

        if instance:
            return Action(instance, run, is_property=True)
        else:
            return self.query


class ServiceBase(type):
    """
    Metaclass for Service. This takes mostly care of wrapping Service members
    into the correct descriptor, but it does some metaclass magic.
    """
    # Keep track of the order in which services are created, so that we can
    # retain the order of nested sub services. This global variable is
    # increased after every definition of a Service class.
    creation_counter = 0

    def __new__(cls, name, bases, attrs):
        # No multiple inheritance allowed.
        if len(bases) > 1:
            # Not sure whether this is a good idea or not, it might be not that bad...
            raise Exception('No multiple inheritance allowed for Services')

        # Default action, if one was defined is some of the bases, use that one.
        default_action = getattr(bases[0], '_default_action', None)

        if name != 'Service':
            # Do not allow __init__ to be overriden
            if '__init__' in attrs:
                raise Exception('A Service should not contain its own __init__ function, just leave Service.__init__ alone')

            # Replace actions/subservices/properties by descriptors
            for attr_name, attr in attrs.items():
                wrapped_attribute = cls._wrap_attribute(attr_name, attr, name)
                attrs[attr_name] = wrapped_attribute

                if isfunction(attr):
                    # Handle the default_action param
                    if getattr(attr, 'default_action', False):
                        default_action = attr_name

                    # Create aliases
                    if hasattr(attr, 'action_alias'):
                        for a in attr.action_alias:
                            attrs[a] = wrapped_attribute

                # Make sure that Meta a a class, and if it does not yet
                # inherit from Service.Meta, make sure is does.
                if attr_name == 'Meta':
                    if not isclass(attr):
                        raise Exception('Service.Meta should be a class definition')
                    if not issubclass(attr, Service.Meta):
                        attrs[attr_name] = type('Meta', (attr, Service.Meta), { })

                # If Hosts have been given, make sure it is a class definition.
                if attr_name == 'Hosts':
                    if not isclass(attr):
                        raise Exception('Service.Hosts should be a class definition')

        # Every service should have a 'roles' tuple
        if not isinstance(attrs.get('roles', ()), tuple):
            raise Exception('Service %s does not have a tuple hosts' % name)

        # Set creation order
        attrs['_service_creation_counter'] = cls.creation_counter
        cls.creation_counter += 1

        # Set default action for deployment shell.
        attrs['_default_action'] = default_action

        # Set creation date
        attrs['_creation_date'] = datetime.datetime.now()

        # Make sure that no other variable then the following are used in a
        # Service instance. It has to be stateless between multiple action
        # calls.
        attrs['__slots__'] = ('hosts', 'parent', '_creator_service', '_is_isolated',
                                '_creation_date', '_name', '_path')

        # Create class
        return type.__new__(cls, name, bases, attrs)

    @classmethod
    def _wrap_attribute(cls, attr_name, attribute, service_name):
        """
        Wrap a Service attribute into the correct descriptor class.
        """
        # Wrap functions into an ActionDescriptor
        if isfunction(attribute):
            return ActionDescriptor(attribute)

        # Wrap Services into a ServiceDescriptor
        elif isclass(attribute) and issubclass(attribute, Service):
            return ServiceDescriptor(attribute)

        # Properties should be wrapped again in an Action
        # descriptor
        elif isinstance(attribute, property):
            if isinstance(attribute, required_property):
                attribute.name = attr_name
                attribute.owner = service_name
            return PropertyDescriptor(attribute)

        # Query objects are like properties and should also be
        # wrapped into a descriptor
        elif isinstance(attribute, Query):
            return QueryDescriptor(service_name, attr_name, attribute)

        else:
            return attribute

    def __setattr__(self, name, value):
        """
        When dynamically, a new function/property/class is assigned to a
        Service class definition, wrap it into the correct descriptor, before
        assigning it to the actual class.
        Note that `self` is a Service class here, not a Service instance.
        """
        wrapped_attribute = self._wrap_attribute(name, value, self.__name__)
        type.__setattr__(self, name, wrapped_attribute)


class Env(object):
    """
    Instead of 'self', we give each Service method an instance of
    this class as the first parameter.
    """
    def __init__(self, service, pty=None, logger=None, is_sandbox=False):
        self._service = service
        self._pty = pty or DummyPty()
        self._logger = logger or DummyLoggerInterface()
        self._is_sandbox = is_sandbox

    def __repr__(self, path_only=False):
        path = self._service.__repr__(path_only=True)
        if path_only:
            return path
        else:
            return '<Service Env %s>' % path

    def __eq__(self, other):
        return getattr(self, '_service', None) == getattr(other, '_service', None)

    @property
    def hosts(self):
        return HostsContainer(self._service.hosts._hosts, self._pty, self._logger, self._is_sandbox)

    @property
    def host(self):
        """
        HostContainer object for isolated services. This works well with the
        @isolate_host decorator. When a `isolate_role' has been set for a
        service, the host which is currently in this isolation will be
        available through here.
        """
        # When this service has been isolated, `self.host' refers to the
        # current host in the isolation role.
        if self.is_isolated and self._service.Meta.isolate_role:
            host = self._service.hosts.get(self.Meta.isolate_role)._hosts
            return HostContainer(host, self._pty, self._logger, self._is_sandbox)
        else:
            raise AttributeError

    @property
    def parent(self):
        if self._service.parent:
            return Env(self._service.parent, self._pty, self._logger, self._is_sandbox)
        else:
            return None

    @property
    def is_isolated(self):
        """
        True when this service is running isolated. That means that only one
        host will be in the isolated role.
        If True, this also means that Calling an action of this service, will
        return one result. Calling an action of a not-yet isolated service
        (for intance, a nested service) will return a list of results. Namely,
        one for each isolation. Calling an action of a host which doesn't have
        an Meta.isolate_role setting, always only one result is returned.
        """
        return self._service._is_isolated

    @property
    def super(self):
        """
        super property does not work, use following construct:
        >> MySuperService.action(self, ...)

        This will never work:
        >> super(MyService, self).action(...) # Because the super-proxy is not compatible.

        I still want to implement it this way:
        >> self.super.action(...)
        """
        raise NotImplementedError # Does not yet work...

        #return self._service.__class__.__bases__

        #print super(self._service.__class__, self._service)
        return Env(super(self._service.__class__, self._service), self._pty, self._logger, self._is_sandbox)

    @property
    def fork(self):
        """
        Return a fork-proxy. An object, identical to this service Env, with the difference that
        when an action on the object is executed, it will run in a new thread, in another Pty.

        The result of a fork call, will always be a ForkResult object. An object wich a join-method
        in order to wait for the result of this call. and a 'result' member with the actual result.

        e.g, you can write in a Service's action:

        >> class Myservice(Service):
        >>     def some_action(self):
        >>         self.fork.some_other_action() # Run this action in parallel, in another thread.
        >>
        >>     def some_other_action(self):
        >>         pass
        """
        class ForkProxy(object):
            def __init__(proxy, getobj, getname):
                proxy.__getobj = getobj
                proxy.__getname = getname

            def __getattr__(proxy, key):
                return ForkProxy(
                        lambda pty, logger: getattr(proxy.__getobj(pty, logger), key),
                        lambda: "%s.%s" % (proxy.__getname(), key))

            def __call__(proxy, *a, **kw):
                forkname = proxy.__getname()

                # Ask before forking in sandboxed mode.
                if self._is_sandbox and input('Do you want to fork %s in sandbox?' % forkname, answers=['y', 'n']) == 'n':
                    return

                # Fork logger
                logger_fork = self._logger.log_fork(forkname)

                def callback(pty):
                    try:
                        # TODO: raise exception if proxy.__getobj does not return an Action.
                        proxy.__getobj(pty, logger_fork.get_logger_interface())(*a, **kw)

                        logger_fork.set_succeeded()
                    except Exception, e:
                        logger_fork.set_failed(e)
                        print e # TODO: handle this exception like Action._run_action in the deployment_shell.py
                                #       show better feedback

                        # Wait for the user to press enter. (This will close
                        # this thread, and so the pane when being forked.)
                        raw_input('Continue...')

                fork_result = self._pty.run_in_auxiliary_ptys(callback)
                return fork_result

        def getobj(pty, new_logger):
            # Create a new service instance, with a clone of all hosts.
            new_service = self._service.__class__(self._service.hosts.clone(), name=self._service._name, path=self._service._path,
                                                        parent=self._service.parent, creator_service=self._service)
            return Env(new_service, pty, new_logger, is_sandbox=self._is_sandbox)

        def getname():
            return self._service.__class__.__name__

        return ForkProxy(getobj, getname)

    def isinstance(self, class_):
        return isinstance(self._service, class_)

    def __call__(self, *a, **kw):
        self._service(*a, **kw).run(self._pty, self._logger)

    def get_subservices(self):
        for name, subservice in self._service.get_subservices():
            yield name, self.get_subservice(name)

    def get_group(self):
        return self._service.get_group()

    def get_actions(self):
        for name, action in self._service.get_actions():
            yield name, self.get_action(name)

    def get_action(self, name):
        """
        Retrieve service action from within the environment, this does not
        require calling sandbox/run on the action result.
        """
        action = self._service.get_action(name)

        @wraps(action._func)
        def func(*a, **kw):
            if self._is_sandbox:
                return action(*a, **kw).sandbox(self._pty, self._logger)
            else:
                return action(*a, **kw).run(self._pty, self._logger)

        if action.is_property:
            # Properties are automatically called upon retrieval
            return func()
        else:
            return func

    def get_subservice(self, name):
        subservice = self._service.get_subservice(name)
        return Env(subservice,self._pty, self._logger, self._is_sandbox)

    def get_isolations(self):
        for i in self._service.get_isolations():
            i.service = Env(i.service, self._pty, self._logger, self._is_sandbox)
            yield i

    def __getitem__(self, name):
        subservice = self._service[name]
        return Env(subservice,self._pty, self._logger, self._is_sandbox)

    def initialize_service(self, service_class, mappings=None, name=None):
        """
        Dynamically initialize a service from within another service.
        This will make sure that the service class is initialized with the
        correct logger, sandbox and pty settings.

        - service_class, on object, inheriting from Service
        - mappings: a dict which maps the roles on host containers (or Host
                      instances)
        - name: custome name for this service.

        Note that when the service_class has a 'Hosts' definition inside,
        this will always get priority above **mappings.
        """
        mappings = mappings or { }
        name = name or service_class.__name__

        # Transform mappings (can both be Host classes, or host container objects.)
        for role, v in mappings.items():
            if isclass(v) and issubclass(v, Host):
                mappings[role] = [ v.get_instance() ]
            elif isinstance(v, (list, tuple)):
                mappings[role] = [ i.get_instance() for i in v ]
            elif isinstance(v, HostsContainer):
                mappings[role] = v._all

        # Initialize service
        service_instance = service_class(HostsContainer(mappings), creator_service=self._service, name=name)

        # Wrap in Env
        return Env(service_instance, self._pty, self._logger, self._is_sandbox)

    def __getattr__(self, name):
        # When one action call another action within the same
        # service. Run it immediately.
        if self._service.has_action(name):
            return self.get_action(name)

        # When one action calls another sub service,
        # Return a proxy to one such instance.
        if self._service.has_subservice(name):
            return self.get_subservice(name)

        # Access to other class properties
        else:
            # Direct access to other Service members is still allowed.
            return getattr(self._service, name)

    def __setattribute__(self, name, value):
        raise AttributeError('You cannot save anything in the environment object. Service classes should be kept stateless.')


class Action(object):
    """
    Service actions, which are defined as just functions, will be wrapped into
    this Action class. When one such action is called, this class will make
    sure that a correct 'env' object is passed into the function as its first
    argument.
    """
    def __init__(self, service, func, is_property=False):
        self._service = service
        self._func = func
        self._is_property = is_property

    def __repr__(self):
        if self._service:
            return "<Action %s.%s>" % (self._service.__repr__(path_only=True), self._func.__name__)
        else:
            return "<UnboundAction %s>" % self._func.__name__

    @property
    def service(self):
        return self._service

    @property
    def name(self):
        return self._func.__name__

    @property
    def full_name(self):
        if self._service:
            return '%s.%s' % (self.service.__repr__(path_only=True), self.name)
        else:
            return '<Unbound>.%s' % self.name

    def get_group(self):
        return self.service.get_group()

    @property
    def is_unbound(self):
        """
        When the action descriptor has been called from a Service
        class, instead of a service instance.
        e.g.
            SomeService.action(current_env, *a, **kw)
        instead of
            current_env.action(*a, **kw)
        """
        return not self._service

    @property
    def supress_result(self):
        return getattr(self._func, 'supress_result', False)

    def autocomplete(self, text):
        """
        Autocomplete function action.
        >> Service(...).action.autocomplete('text')
        """
        assert not self.is_unbound

        if hasattr(self._func, 'autocomplete'):
            env = Env(self._service, None, None, is_sandbox=True)
            return self._func.autocomplete(env, text)
        else:
            return []

    @property
    def is_property(self):
        return self._is_property

    def help(self):
        """
        Return help text for this action.
        >> Service('...').action.help()
        """
        assert not self.is_unbound

        if hasattr(self._func, 'help'):
            env = Env(self._service, None, None, is_sandbox=True)
            return self._func.help(env)
        else:
            # getdoc uses cleandoc for removing indentation.
            return inspect.getdoc(self._func)

    def __call__(self, *args, **kwargs):
        """
        Call the action:
        >> Service('...').action()
        """
        # Extract _trace_action from kwargs
        trace_action = kwargs.get('_trace_action', False)
        kwargs = kwargs.copy()
        if trace_action:
            del kwargs['_trace_action']

        # Name of this action call, to be passed to the loggers.
        service = self._service
        func = self.full_name
        from_env = None

        # Unbound??
        if self.is_unbound:
            # When unbound, we both support the first argument to be a
            # Service instance, and Env instance. When it is a Service
            # instance, a CalledAction will be returned. If it is an Env
            # instance, we suppose calling from within another 'env',
            # and will call it, using the same environment settings.
            if isinstance(args[0], Service):
                service = args[0]
            else:
                # args[0] should be a Env instance
                from_env = args[0]
                service = args[0]._service
            args = args[1:]

        class CalledAction(object):
            """
            Action called with parameters, but not really
            executed yet. Either a 'run' or 'sandbox' call
            on this object will execute the real action.
            """
            def __repr__(a):
                return '<CalledAction %s.%s(...)>' % (self.service.__repr__(path_only=True), self.name)

            def _run(a, pty=None, logger_interface=None, sandboxed=False):
                # Fall back to default pty/logger
                pty = pty or Pty()
                logger_interface = logger_interface or DummyLoggerInterface()

                # When we still have to enter isolation...
                # Execute separately for each isolation and return List.
                if service._is_isolated or getattr(self._func, 'dont_isolate_yet', False):
                    # Not to be isolated. Just return the result.
                    return a._run_on_service(pty, logger_interface, sandboxed, service)

                else:
                    isolations = list(get_isolations(service))

                    isolate_role = service.Meta.isolate_role

                    # NOTE: No host in the isolation role? Don't do anything!
                    if len(isolations) == 0:
                        print ('*** No hosts mapped to isolate_role %s of %s. Nothing to do.' %
                                                (isolate_role, service.__class__))

                    # Only one cell -> run in current context
                    elif len(isolations) == 1:
                        return [ a._run_on_service(pty, logger_interface, sandboxed, isolations[0].service) ]

                    # Multiple cells, but need to be run on only one.
                    elif len(isolations) > 1 and getattr(self._func, 'isolate_one_only', False):
                        # Ask the end-user which one to use.
                        from deployer.console import select_service_isolation
                        isolation_service = select_service_isolation(service)

                        # This this action on the new service.
                        return [ a._run_on_service(pty, logger_interface, sandboxed, isolation_service) ]

                    # Otherwise, fork for each isolation.
                    elif len(isolations) > 1:
                        errors = []

                        # Create a callable for each host.
                        def closure(isolation):
                            def call(pty):
                                # Fork logger
                                logger_fork = logger_interface.log_fork('On: %s' % isolation.name)

                                try:
                                    # Run this action on the new service.
                                    result = a._run_on_service(pty, logger_interface, sandboxed, isolation.service)

                                    # Succeed
                                    logger_fork.set_succeeded()
                                    return result
                                except Exception, e:
                                    # TODO: handle exception in thread
                                    logger_fork.set_failed(e)
                                    errors.append(e)
                            return call

                        # For every possible isolation, create a callable.
                        callables = [ closure(i) for i in isolations ]

                        print 'Forking %s (%i pseudo terminals)' % (self._func.func_name, len(callables))

                        fork_result = pty.run_in_auxiliary_ptys(callables)
                        fork_result.join()

                        # When an error occcured in one fork, raise this error
                        # again in current thread.
                        if errors:
                            raise errors[0]
                            #raise Exception('Fork errors: %s' % str(errors)) # TODO: better exception handling.
                        else:
                            return fork_result.result # Return list of results

            def _run_on_service(a, pty, logger_interface, sandboxed, service):
                # Trace everything using additional logger
                trace = TraceLogger()

                with logger_interface.attach_in_block(trace):
                    with logger_interface.group(func, *args, **kwargs):
                        with capture() as capt:
                            # Make env
                            env = Env(service, pty, logger_interface, sandboxed)

                            # Run command
                            try:
                                # Call real func
                                result = self._func(env, *args, **kwargs)

                                # TODO: add retry/fail/skip flow control here
                                # in case of error.

                                # Return result
                                if self._is_property:
                                    return result

                                elif trace_action:
                                    return ActionResult(result, capt.value, trace.first_trace) # TODO: include isolation name.
                                else:
                                    return result

                            # When something goes wrong, wrap exception in
                            # 'ActionException', this allows inspection of the
                            # execution trace.
                            except ActionException, e:
                                raise ActionException(e.inner_exception, e.traceback, capt.value, trace.first_trace)
                            except Exception, e:
                                raise ActionException(e, traceback.format_exc(), capt.value, trace.first_trace)

            def run(a, pty=None, logger=None):
                """
                Execute action.
                """
                return a._run(pty, logger, False)

            def sandbox(a, pty=None, logger=None):
                """
                Execute action in sandbox environment
                """
                try:
                    return a._run(pty, logger, True)
                except ActionException, e:
                    # Just let ActionExceptions propagate.
                    raise e
                except Exception, e:
                    # When an exception was raised during sandboxing,
                    # show exception and ask the user whether to continue
                    print traceback.format_exc()
                    print
                    print 'An exception was raised during *sandboxed* execution.'
                    print 'If you go on, the simulation will possibly be different from real execution.'

                    if input('Go on?', answers=['y', 'n']) == 'n':
                        raise e

        # When an action is called unbound, but with the first parameter
        # an 'Env' object, call it direct. e.g.
        # >> Service.action(env, ...)
        # Where Service is the class, not an instance.
        if self.is_unbound and from_env:
            called_action = CalledAction()
            if from_env._is_sandbox:
                return called_action.sandbox(from_env._pty, from_env._logger)
            else:
                return called_action.run(from_env._pty, from_env._logger)

        # Otherwise, just return the CalledAction object.
        else:
            return CalledAction()


def get_isolations(service):
    """
    Split this service instance into a list of services according to their
    isolation rules. This works recursively top-down from the parent service.
    """
    # If this service has host definitions, than we don't need to isolate the
    # parent, or redo any host mappings.
    service_has_host_definitions = hasattr(service, 'Hosts')

    class Isolation(object):
        def __init__(self, name, service):
            self.name = name
            self.service = service

    # The parent may not yet have been isolated, and therefore,
    # this may be a list of parents, causing this action to be
    # actually a list of actions.
    if service.parent and not service.parent._is_isolated and not service_has_host_definitions:
        parents = list(get_isolations(service.parent))
    else:
        parents = [ Isolation('', service.parent) ] # service.parent can still be None

    # For every parent
    for parent_isolation in parents:
        parent_name = [ parent_isolation.name ] if parent_isolation.name else []

        # Redo role mapping from parent (if we have a parent service, and
        # don't have our own host definitions.)
        if parent_isolation.service and not service_has_host_definitions:
            hosts = HostsContainer(service.__class__.Meta.role_mapping.apply(parent_isolation.service))
        else:
            hosts = service.hosts

        def create_isolation(name, hosts_dict):
            """
            Isolation creator helper. Creates instances of Service classes,
            passing a new hosts dictionary.
            """
            name = '.'.join(name)

            # Nameless isolations are just isolated copies of the non-isolated
            # services.
            if name:
                service_name = '[%s]' % name
                service_path = service._path + [service]
            else:
                service_name = service._name
                service_path = service._path

            return Isolation(name, service.__class__(hosts_dict,
                                    name=service_name,
                                    path=service_path,
                                    parent=parent_isolation.service,
                                    creator_service=service, is_isolated=True))

        isolate_role = service.Meta.isolate_role

        if isolate_role and not service._is_isolated:
            # When @map_roles.just_one
            if service.__class__.Meta.role_mapping.assert_just_one_isolation:
                hosts_in_isolation_role = len(hosts.filter(isolate_role))

                if hosts_in_isolation_role == 1:
                    yield create_isolation(parent_name, hosts)
                else:
                    # When @map_roles.just_one fails, we don't yield this
                    # service, and so disallow access due to invalid mapping.
                    print '*** Warning: @map_roles.just_one got %i hosts for role %s in %s' % (
                                    hosts_in_isolation_role, isolate_role, repr(service))

            # Otherwise
            else:
                # Yield all isolations of this service.
                if len(hosts.filter(isolate_role)):
                    for h, hosts2 in hosts.iterate_isolations(isolate_role):
                        yield create_isolation(parent_name + [h.slug], hosts2)
        else:
            # Just link to new parent.
            yield create_isolation(parent_name, hosts)


class ActionResult(object):
    """
    When an action within a service is called and the _trace_action parameter
    is given, it will return an ActionResult, This is a wrapper around the
    real return value, which contains also the captured stdout.
    """
    def __init__(self, result, output, trace):
        # Return value
        self.result = result

        # Output written to stdout
        self.output = output

        # Trace of executed actions within this block
        self.trace = trace

    def __unicode__(self):
        return unicode(self.result)

    def __str__(self):
        return str(self.result)


class ActionException(Exception):
    """
    When an action fails.
    """
    def __init__(self, inner_exception, traceback, output, trace):
        self.inner_exception = inner_exception
        self.traceback = traceback
        self.output = output
        self.trace = trace

    def __str__(self):
        return str(self.inner_exception)


class Service(object):
    """
    Parent class for every deployment service.

    There are three places where this class can be initialised.
    1. The root service class will be initialised by an interactive deployment shell, an external
       library, or any other starting point.
    2. In a ServiceDescriptor. When a service is nested inside another one,
       it's the service descriptor which takes care of the initialisation of
       the nested service.
    3. In get_isolations.
    """
    __metaclass__ = ServiceBase

    class Meta(object):
        # By default, just one role, named 'host'
        roles = ('host',) # Should be a tuple of role-slugs

        # And allow parallel deployments when multiple hosts are given for
        # this role.
        isolate_role = None # Should be a role-slug or None, typically, this is just 'host'

        # TODO: allow a tuple of roles to be isolated. e.g. for the Postgres
        # database, you want master and slave to be addressed separately, even
        # when they have different roles. But (!) you want the other hosts to
        # be available through an alias, e.g. 'all:master' or 'all:slave'

        # Assign this service to a group (Production, Staging, Development, ...)
        # None will take the service group from the parent or fall back to default.
        group = None

        # Extra loggers for things happening in here.
        # (Right now, these are only taken into account for the root service.)
        extra_loggers = []

        # Role mapping function
        role_mapping = map_roles.create_role_mapping()

    # Optionally, a Hosts object can be placed in here.
    # Typically, for the root Service, which don't have a parent to map from.

    # class Hosts(object):
    #     pass

    def __init__(self, hosts=None, name=None, path=None, parent=None, creator_service=None, is_isolated=False):
        """
        'hosts` should always be a HostContainer object.
        'name` is the string of the property, how we got to this service.
        'path` is the list of parent services through which we passed to get here.
                    (Note that equels not necessary [.parent/.parent.parent/etc... ].)
        'parent` can be a Service instance.
        'creator` can be a Service instance.
        """
        # When a Hosts object exists in this service, use that one, and ignore
        # the hosts which are passed in this constructor. So, any host
        # mappings do not apply
        if hasattr(self.__class__, 'Hosts'):
            def get_hosts_container():
                hosts = { }
                for k in dir(self.__class__.Hosts):
                    v = getattr(self.__class__.Hosts, k)

                    if isclass(v) and issubclass(v, Host):
                        hosts[k] = [ v.get_instance() ]
                    elif isinstance(v, (list, tuple)):
                        hosts[k] = [ i.get_instance() for i in v ]
                return HostsContainer(hosts)

            self.hosts = get_hosts_container()

        # Otherwise, take hosts from the parent host mapping.
        else:
            self.hosts = hosts or HostsContainer({ })

        self._path = path or []
        self._name = name
        self.parent = parent
        self._creator_service = creator_service
        self._is_isolated = is_isolated

    def __repr__(self, path_only=False):
        """
        Service repr. Contains the full name.
        """
        if self._name:
            path = '.'.join([ s._name or '{%s}' % s.__class__.__name__ for s in self._path ] + [ self._name ])
        else:
            path = '{%s}' % self.__class__.__name__

        return path if path_only else '<Service %s>' % path

    @property
    def root(self):
        """
        Go up through the parents and grandparents of this service, and return the root.
        """
        node = self
        while node.parent:
            node = node.parent
        return node

    def get_actions(self):
        """
        Yield all the available actions. Yields tuples of (name, Action callable.)
        (Except the private ones)
        """
        for name, member in inspect.getmembers(self):
            if not name.startswith('_') and isinstance(member, Action) and not getattr(self, name).is_property:
                yield name, getattr(self, name)

    def get_subservices(self):
        """
        Yield the available nested subservices. Returns tupels of (name, subservice_instance)
        (Except the private ones)

        (for use in the deployment shell)
        """
        # Sub services
        for name, member in inspect.getmembers(self):
            if not name.startswith('_') and name != 'parent':
                if isinstance(member, Service):
                    yield name, getattr(self, name)

        # Isolations also act as subservices.
        if self.Meta.isolate_role and not self._is_isolated:
            for i in get_isolations(self):
                yield ':%s' % i.name, i.service

    def has_subservice(self, name):
        """
        (for use in the deployment shell)
        """
        # Name starts with a colon -> adressable self
        if name.startswith(':') and not self._is_isolated:
            # Return true when a host with this slug exists in the isolate role.
            return any(i.name == name[1:] for i in get_isolations(self))

        # Subservice attributes.
        elif hasattr(self, name) and isinstance(getattr(self, name), Service):
            return True

        return False

    def get_subservice(self, name):
        """
        (for use in the deployment shell)
        """
        # Starting with ':' -> this is an addressing.
        if name.startswith(':') and not self._is_isolated:
            for i in get_isolations(self):
                if i.name == name[1:]:
                    return i.service

        # Normal subservices
        if self.has_subservice(name):
            return getattr(self, name) # Normal service
        else:
            raise AttributeError

    def has_action(self, name):
        return hasattr(self, name) and isinstance(getattr(self, name), Action)

    def get_action(self, name):
        if self.has_action(name):
            return getattr(self, name)
        else:
            raise AttributeError

    def get_isolations(self):
        return get_isolations(self)

    def get_group(self):
        """
        Return the group to which this service belongs.
        """
        service = self
        while True:
            # If we found a group, return it
            if service.Meta.group:
                return service.Meta.group

            # Otherwise move up to the parent
            elif service.parent:
                service = service.parent

            # Or the creator.
            elif service._creator_service:
                service = service._creator_service

            else:
                return Group

    def __getitem__(self, name):
        """
        Return a certain isolation.
        name can be either:
        - a slug of the isolation
        - a list index (integer)
        - a HostContainer object.
        """
        if self.Meta.isolate_role and not self._is_isolated:
            if isinstance(name, basestring):
                return self.get_subservice(':%s' % name)
            elif isinstance(name, int):
                hosts = self.hosts.filter(self.Meta.isolate_role)
                return self.get_subservice(':%s' % hosts[name].slug) # TODO: check for nested isolation rules.
            elif isinstance(name, Host):
                                # TODO: this is not entirely correct. Check for
                                #       nested isolation rules.
                return self.get_subservice(':%s' % name.slug)
            elif isinstance(name, HostContainer):
                return self.__getitem__(name._host)
            else:
                raise AttributeError
        else:
            raise TypeError('%s has no Meta.isolate_role or was already isolated.' % repr(self))

    def __len__(self):
        if self.Meta.isolate_role and not self._is_isolated:
            return sum(1 for _ in get_isolations(self))

        else:
            raise AttributeError

    def __nonzero__(self):
        # Otherwise, "if <service>:..." would cause __len__ to be called,
        # which can raise AttributeError
        return True



# ======================[ Service decorators ]=====================

def isolate_role(role):
    """
    Turn on role isolation on a service for this role.
    Usage:
    >> @isolate_role('host')
    >> class MyService(Service):
    >>     ...
    """
    assert not role or isinstance(role, basestring)

    # Create decorator
    def isolate_decorator(service):
        # Don't modify the class, but create a new definition instead.
        new_meta = type('Meta', (service.Meta, ), { 'isolate_role': role })
        return type(service.__name__, (service,), { 'Meta': new_meta })

    # Add doc
    isolate_decorator.__doc__ = 'Turn on host isolation for the role "%s"' % role

    return isolate_decorator

# Some helper decorators:
#   @isolate_host
#   @dont_isolate

isolate_host = isolate_role('host')
dont_isolate = isolate_role(None)


# ======================[ Action decorators ]=====================

def supress_action_result(action):
    """
    When using a deployment shell, don't print the returned result to stdout.
    For example, when the result is superfluous to be printed, because the
    action itself contains already print statements, while the result
    can be useful for the caller.
    """
    action.supress_result = True
    return action


def default_action(func):
    """
    Mark this action as the default action for the deployment shell, this
    means that no other actions into this service can be called from there.
    """
    func.default_action= True
    return func


def dont_isolate_yet(func):
    """
    If the service has not yet been separated in serveral parallel, isolated
    services per host. Don't do it yet for this function.
    When anothor action of the same host without this decorator is called,
    the service will be split.

    It's for instance useful for reading input, which is similar for all
    isolated executions, (like asking which Git Checkout has to be taken),
    before forking all the threads.

    Note that this will not guarantee that a service will not be split into
    its isolations, it does only say, that it does not have to. It is was
    already been split before, and this is called from a certain isolation,
    we'll keep it like that.
    """
    func.dont_isolate_yet = True
    return func


def isolate_one_only(func):
    """
    When using role isolation, and several hosts are available, run on only
    one role.  Useful for instance, for a database client. it does not make
    sense to run the interactive client on every host which has database
    access.
    """
    func.isolate_one_only = True
    return func


def alias(name):
    """
    Give this service action an alias. It will also be accessable using that
    name in the deployment shell. This is useful, when you want to have special
    characters which are not allowed in Python function names, like dots, in
    the name of an action.
    """
    def decorator(func):
       if hasattr(func, 'action_alias'):
           func.action_alias.append(name)
       else:
           func.action_alias = [ name ]
       return func
    return decorator


# ======================[ Utilities ]=============================

class required_property(property):
    """
    Placeholder for properties which are required
    when a service is inherit.
    """
    def __init__(self, description=''):
        self.description = description
        self.name = ''
        self.owner = ''

        def fget(obj):
            raise NotImplementedError('Property %s of %s is not defined: %s' % (self.name, self.owner, self.description))

        property.__init__(self, fget)

