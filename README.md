Deployer
========

The deployer is a Python framework for automatic application deployment on
Posix systems, usually through SSH. When set up, it can be called as a
library, but usually, people use it through an interactive command line.

Some key features are:

 - Interactive execution of remote commands, locally, they will appear in a
   pseudo terminal (created with openpty), so that even editors like Vim or
   Emacs works fine when you run them on the remote end.
 - Reusability of all deployment code is a key point. It's as declarative as
   possible, but without loosing Python's power to express everything as
   dynamic as you'd like to. Deployment code is hierarchically structured, with
   inheritance where possible.
 - Parallel execution is easy when enabled, while keeping interaction with
   these remote processes possible through pseudoterminals. Every process gets
   his own terminal, either a new xterm or gnome-terminal window, a tmux pane, or
   whatever you'd like to.
 - Logging of your deployments. New loggers are easily pluggable into the
   system.

There are still some minor TODO's in the code. Interactive exception handling
(retry/abort) could be improved for instance, but the core is very stable.
Personally, we are using this deployment system successfully for deploying
Django and Twisted webservers to about 40 remote servers, but we have
confidence about the reliability in ever larger systems.

It's recommended to have at least a basic knowledge of the Python language,
before starting to use this framework. We are also not responsible for any
damage done to a computer due to possible bugs in this framework or your
deploment code.

Feel free to fork this project on github. Contributions are always welcome.
Also, any feedback about syntax, API, conventions, documentation, or anything
else is very welcome.


Thanks to
---------

The deployer depends on two major libraries: Paramiko and Twisted Matrix.

A small amount of code was also inspired by Fabric.

Authors
-------

 - Jonathan Slenders (CityLive, Mobile Vikings)

I'd also like to thank my colleague from the operations team, Jan Fabry, for all
his useful feedback.

History
-------

During the summer of 2011, when I was unsatisfied with some of the capabilities
of Fabric, I (Jonathan) started the development of a new, interactive
deployment system from scratch. The first successful deployments (of a Django
project) were done only a few months later, but since then, all the code has
been refactored quite a few times.


Getting started
---------------

    pip install deployer

Normally, you will create your own host definitions (with login credentials),
and connect them somehow to a deployment service. There are quite a few ways
for doing this, but to get a quick feeling of the example shell which
contains some demo code and will connect to localhost, do the following:

    ./deployer/run/standalone_shell.py

This shell has tab-completion. The cyan keywords are build-ins, the other
colours are dynamic and represent your deployment tree.

`ls`, `cd` and `exit` act like you would expect in any other shell.  It's a
hierarchical architecture, in which you can move with `cd`.

There's a second way, to start the shell:

    ./deployer/run/client.py

This looks identical, but the difference is that this one supports parallel
execution. If the deployment framework decides to split work over several
pseudo terminals, this shell can spawn a second terminal window, or split the
current one. It's highly encouraged to use this in conjunction with tmux, the
terminal multiplexer. If it's not running inside tmux, a second xterm window
will be spawned when necessary.


Understanding services
----------------------

A service is a collection of actions and/or subservices, where each action
usually executes one or more commands on one or more hosts.

Take it little time, trying to understand Service definitions. It's quite
powerful.


### A first example

A simple service for installing Debian packages would for instance look like this:

```python
from deployer.service import Service

class AptGet(Service):
    packages = ()

    def update(self):
        self.hosts.sudo('apt-get update')

    def install(self):
        self.hosts.sudo('apt-get install %s' % ' '.join(self.packages))
```

When `AptGet.install` is called, it will install the packages on all the hosts
that are known in this Service.

`self.hosts` is a hosts container. A sudo or run call on this object will cause
it to be executed on every host in this container.

NOTE: It is interesting to know that `self` is actually not a Service instance,
      but an `Env` object which will proxy this actual Service class. This is
      because there is some metaclass magic going on, which is required for
      sandboxing and some internal workings like the service class initialisation
      and the logging.

Usually, installing of packages is part of a larger deployment. You can for instance
nest this class into your web application Servics as follows:

```python
from deployer.contrib.services.apt_get import AptGet

class MyWebApplication(Service):
    class packages(AptGet):
        packages = ('python', 'gcc')

    def setup(self):
        self.packages.setup()

    def say_hello(self):
        self.hosts.run('echo hello world')

    def start(self):
        self.hosts.run('~/start-application.sh')
```

In this case, if you need to, you can use the variable `self.parent` in the
inner class to refer to the outer class instance.


### Adding hosts

This service definition does not yet know on which host or hosts in need to
run.

1. Create host definitions like this:


```python
from deployer.host import SSHHost

class MyHost(SSHHost):
    slug = 'my-host'
    address = '192.168.0.200'
    username = 'john'
    password = '...'
```

2. Add this hosts to the service.

```python
class MyWebApplicationWithHosts(MyWebApplication):
    class Hosts:
        host = [ MyHost ]
```

The will assign `MyHost` to the role `host` of MyWebApplication. Of course you don't have to inherit this `Service`-class once again before you can assign `Hosts`.


3. Creating a shell for this service.

```python
from deployer.run.standalone_shell import start

start(MyWebApplicationWithHosts)
```

### Inheritance

A service is meant to be reusable. It is encouraged to inherit from such a
service class class and overwrite properties or class members.

### contrib.services

The deployer framework is delivered with some contrib services, which are ready
to use. It's certainly not discouraged to stay away from these. They may be
useful for some people, but not for everyone. They may also be good examples of
how to do certain things. Don't be afraid to look at the source code, you can
learn some good practices there. Take these and inherit as you want to, or
start from scratch if you prefer that way.

Some recommended contribe services:

 - `deployer.contrib.services.config.Config`
   This a the base class that we are using for every configuration file. It is
   very useful for when you are automatically generating server configurations
   according to specific deployment configurations. Without any efford, this
   class will allow you to do `diff`s between your new, generated config, and
   the config that's currently on the server side.
 - TODO: add some others.


Mapping hosts to services
-------------------------

You already know that a Service class can act on several hosts.
The great thing is that you can assign roles to these hosts. For instance:

```python
class database(Service):
    class Meta(Service.Meta):
        roles = ('master', 'slaves')

    def do_something(self):
        self.hosts.filter('master').run('echo hello')
```

Two roles were defined, named 'master' and 'slaves'. `self.hosts`, which is
a queriable `HostsContainer` object, can be filtered on either of this roles now.

Suppose that we assign some hosts to the master-role, and some to the
slaves-role, and that we nest another service definition in this database
class. Then we can also do a custom mapping from the parent class to the child
class.

```python
class database(Service):
    class Meta(Service.Meta):
        roles = ('master', 'slaves')

    @map_roles(worker='slaves')
    class worker_things(Service):
         class Meta(Service.Meta):
             roles = ('worker', )

         def do_some_other_things(self):
             pass

    def do_something(self):
        pass
```

All the hosts in the `slaves' role in the database class, can here also be
found in the role 'worker' in the worker_things class.

### Host isolation

Host isolation may be a little hard to understand, but it's quite powerful,
once you grasp the concept. And it's highly recommended trying to understand
this.

Suppose that you have one service with 10 hosts assigned to a certain role.
Often these hosts will be managed completely independent. They are doing
exactly the same thing, but independent, just in parallel. No change on one
host will have any influence on the other hosts.  If you have such a situation,
deployment can be optimized, by running the same set of commands on every of
the 10 hosts in parallel.

The only thing you need to do, is tell the Service which role contains the
hosts that can be isolated. This would be the role that contained the 10 hosts.
If any other role exists, 10 isolations will be created as well, but the other
roles will contain all the hosts like given, every time exactly the same.

The `Meta.isolate_role` property does exactly that.

```python
class database(Service):
    class Meta(Service.Meta):
        roles = ('master', 'slaves')

    @map_roles(host='slaves')
    class config_on_slaves(Service):
         class Meta(Service.Meta):
             roles = ('host', )
             isolate_role = 'host'

         def setup(self):
             pass
```

From the database class's point of view. `config_on_slaves` will now behave
like an array, instead of a single service. Calling `config_on_slaves.setup()`
would return an array of results. Because for every isolation (with their
host), the function will be executed once.

Instead of overriding the `Service.Meta` class, it is recommended to use the `isolate_role('host')` or `isolate_host` decorator, like this:

```python
from deployer.service import isolate_host

class database(Service):
    class Meta(Service.Meta):
        roles = ('master', 'slaves')

    @isolate_host
    @map_roles(host='slaves')
    class config_on_slaves(Service):
         def setup(self):
             pass
```

#### map_roles.just_one

Normally, when you are using host_isolation, the inner Service will behave like
an array from the point of view of the outer Service. However, sometimes, when
you are reusing services, you will get to a point where you are nesting two
services which are isolating on the same role. In that case, you're sure that
there will always be exactly one instance of the inner service, for every
instance of the outer service. The decorator `map_roles.just_one` will make
sure that you don't have to place `[0]` after accessing properties of the inner
service.

Example:


```python
from deployer.service import isolate_host

@isolate_host
class outer_service(Service):
    @isolate_host.just_one
    class inner_service(Service):
         property = value

         def setup(self):
             pass

    def setup(self):
        # This is not an array (it is when you drop the '.just_one')
        self.inner_service.property

        # This returns also not an array, but a single value.
        self.inner_service.setup()
```

#### `self.hosts` vs. `self.host`

Note that one is plural, the other is singular. In a service action,
`self.hosts` is a `HostsContainer` object. If you call `run` or `sudo` on this
object, the framework will run this command on every host in this container.
The container also has a `.filter(role)` function for reducing the set of hosts
in this container according to the role or roles you are passing.

`self.host` is also a HostsContainer object, but will only be available if the
`@isolate_host` decorator or the `Meta.isolate_role` was set. This container
object will only contain the host in the current isolation instance.


The Q object
-------------------

The `Q` object is syntactic sugar for `@property`.

Suppose you have:

```python
class A(Service):
    @property
    def b(self):
        return self.c
```

No calculation is going on in the property, it's just a retrieval of another field.
You can write this as:

```python
class A(Service):
    b = Q.c
```


Some more sugar. This:
```python
class A(Service):
    @property
    def b(self):
        return self.parent.c[4].d % 'test'
```

can be written as:
```python
class A(Service):
    b = Q.parent.c[4].d % Q('test')
```


The different shells
-------------------

The easiest way to create an interactive shell from a Service, is the following:

```python
from deployer.run.standalone_shell import start

if __name__ == '__main__':
    start(your_service_class)
```

So you pass your root service definition to the `start` method. This
standalone_shell is really reliable but does not support parrallel execution.
Everything is done sequential. We have some other shells, all called by their
`start`-method.

 1. The following is the only approach for parallel execution right now. This
    will spawn a deployer sever in the background, attached to a unix socket.
    (Similar to the tmux model.) At the same time the client will connect to
    this server.  When something needs to be done in parallel, a second client
    is opened in another terminal window. (works very well in tmux, but can
    also open xterm or gnome-terminal.)

```python
from deployer.run.socket_client import start
```

 2. For debugging, it is interesting to start an IPython shell with your root
    service:

```python
from deployer.run.ipython_shell import start
```

 3. There is also a web server which accepts telnet connection for easy
    deployment: (This is working, but needs some refactoring.)

```python
from deployer.web_frontend import start
from deployer.web_frontend.backends import RedisBackend
from citylive_deployments.config import citylive_deployment


if __name__ == '__main__':
    backend = RedisBackend(host='localhost', port=6379)
    backend.create_user('username', 'password')
    start(citylive_deployment, backend)
```


Using as a library
-------------------

The whole deployer framework doesn't save any state in a global variable or
settings module. This means that you can easily use and call several deployer
configurations in the same Python process in parallel.

...


Feature work
------------

* Pipes between processes would be very useful. Instead of just calling
  `host.run('mysqldump ...')` it'd be great to be able to open a pipe to that
  process from which you can read. If you can open at the same time a pipe to
  another process, to write the content to, and we could route the traffic
  between these two end-points in a select loop, then we can stream data from
  one command on one host, to another command on another host.

  That's great for restoring databases from a production server to a staging
  server.

  ```python
  def sync(self):
      p1 = self.production_host.open_process('mysqldump mydatabase')
      p2 = self.staging_host.open_process('mysql', stdin=p1.stdout)
      p2.communicate() # Like the Python subprocess module.
  ```

  This would require some changes to the `host.py` file.
