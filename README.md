Deployer
========

The deployer is a Python framework for automatic application deployment on
Posix systems, usually through SSH. When set up, it can be used as a library or
through the interactive command line.

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

There are still some minor to do's in the code. Interactive exception handling
(retry/abort) could be improved for instance, but the core is very stable.
It's used in production systems consisting of about 50 servers, but thanks to
Paramiko and Twisted it should easily handle bigger set-ups.

It's recommended to have at least a basic knowledge of the Python language,
before starting to use this framework. We are also not responsible for any
damage done to a computer due to possible bugs in this framework or your
deploment code.

Feel free to fork this project on github. Contributions are always welcome.
Also, any feedback about syntax, API, conventions, documentation, or anything
else is very welcome.


Special Thanks to
-----------------

The deployer depends on two major libraries: Paramiko and Twisted Matrix.

A small amount of code was also inspired by Fabric.

Authors
-------

 - Jonathan Slenders (VikingCo, Mobile Vikings)

Special Thanks to:

 - Jan Fabry

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
and connect them somehow to a deployment nodes. There are quite a few ways for
doing this, but to get a quick feeling of the example shell which contains some
demo code and will connect to localhost, do the following:

    ./deployer/client.py run

This shell has tab-completion. The cyan keywords are build-ins, the other
colours are dynamic and represent your deployment tree.

`ls`, `cd` and `exit` act like you would expect in any other shell.  It's a
hierarchical architecture, in which you can move with `cd`.

When the shell detects that somewhere a deployment can be optimized by running
parts in parallel, it will split your terminal window or create new panes and
run part of the deployment job in the other pane. That way, you don't have to
loose any interactivity.


Understanding nodes
-------------------

A node is a collection of actions and/or subnodes, where each action
usually executes one or more commands on one or more hosts.

Take it little time, trying to understand Node definitions. It's quite
powerful.


### A first example

A simple node for installing Debian packages would for instance look like this:

```python
from deployer.node import SimpleNode

class AptGet(SimpleNode):
    packages = ()

    def update(self):
        self.host.sudo('apt-get update')

    def install(self):
        self.host.sudo('apt-get install %s' % ' '.join(self.packages))
```

When `AptGet.install` is called, it will install the packages on all the hosts
that are known in this Node.

NOTE: It is interesting to know that `self` is actually not a Node instance,
      but an `Env` object which will proxy this actual Node class. This is
      because there is some metaclass magic going on, which takes care of sandboxing,
      logging and some other nice stuff, that you get for free.

Usually, installation of packages is part of a larger deployment. You can for instance
nest this class into your web application Servics as follows:

```python
from deployer.contrib.nodes.apt_get import AptGet

class MyWebApplication(SimpleNode):
    class packages(AptGet):
        packages = ('python', 'gcc')

    def setup(self):
        self.packages.setup()

    def say_hello(self):
        self.host.run('echo hello world')

    def start(self):
        self.host.run('~/start-application.sh')
```

In this case, if you need to, you can use the variable `self.parent` in the
inner class to refer to the outer class instance.


### Adding hosts

This node definition does not yet know on which host or hosts it needs to run.

1. Create host definitions like this:

```python
from deployer.host import SSHHost

class MyHost(SSHHost):
    slug = 'my-host'
    address = '192.168.0.200'
    username = 'john'
    password = '...'
```

2. Add this hosts to the node.

```python
class MyWebApplicationWithHosts(MyWebApplication):
    class Hosts:
        host = [ MyHost, MyHost2, ... ]
```

3. Creating an interactive shell for this node.

```python
from deployer.client import start

start(MyWebApplicationWithHosts)
```

Now save all this code in a file, e.g. `my_deployment.py`, and do:

```bash
python my_deployment.py --help
```

```
Usage:
  client.py run [-s | --single-threaded | --socket SOCKET] [--path PATH]
                  [--non-interactive] [--log LOGFILE]
  client.py listen [--log LOGFILE] [--non-interactive] [--socket SOCKET]
  client.py connect (--socket SOCKET) [--path PATH]
  client.py telnet-server [--port=PORT] [--log LOGFILE] [--non-interactive]
  client.py list-sessions
  client.py -h | --help
  client.py --version

Options:
  -h, --help             : Display this help text.
  -s, --single-threaded  : Single threaded mode.
  --path PATH            : Start the shell at the node with this location.
  --non-interactive      : If possible, run script with as few interactions as
                           possible.  This will always choose the default
                           options when asked for questions.
  --log LOGFILE          : Write logging info to this file. (For debugging.)
  --socket SOCKET        : The path of the unix socket.
  --version              : Show version information.
```

This are all the possibe options. Just use the `run` option to start the shell.


### Inheritance

A node is meant to be reusable. It is encouraged to inherit from such a
node class class and overwrite properties or class members.

### contrib.nodes

The deployer framework is delivered with some contrib nodes, which are ready
to use. It's certainly not discouraged to stay away from these. They may be
useful for some people, but not for everyone. They may also be good examples of
how to do certain things. Don't be afraid to look at the source code, you can
learn some good practices there. Take these and inherit as you want to, or
start from scratch if you prefer that way.

Some recommended contribe nodes

 - `deployer.contrib.nodes.config.Config`
   This a the base class that we are using for every configuration file. It is
   very useful for when you are automatically generating server configurations
   according to specific deployment configurations. Without any efford, this
   class will allow you to do `diff`s between your new, generated config, and
   the config that's currently on the server side.
 - TODO: add some others.


Mapping hosts to nodes
----------------------

You already know that a node class can act on several hosts.
The great thing is that you can assign roles to these hosts. For instance:

```python
class database(Node):
    def do_something(self):
        self.hosts.filter('master').run('echo hello')
```

Two roles were defined, named 'master' and 'slaves'. `self.hosts`, which is
a queriable `HostsContainer` object, can be filtered on either of this roles now.

Suppose that we assign some hosts to the master-role, and some to the
slaves-role, and that we nest another node definition in this database
class. Then we can also do a custom mapping from the parent class to the child
class.

```python
class database(Node):
    class Hosts:
        slaves = [ ... ]
        master = [ ... ]

    @map_roles(worker='slaves')
    class worker_things(Node):
         def do_some_other_things(self):
             # Here we have the role `worker` which contains exactly the same hosts
             # as `slaves` in the parent node.
             pass

    def do_something(self):
        # Here we can filter `self.hosts` on both the roles `slaves` and `master`
        pass
```

All the hosts in the `slaves' role in the database class, can here also be
found in the role 'worker' in the worker_things class.

### Host isolation

Host isolation may be a little hard to understand, but it's quite powerful,
once you grasp the concept. And it's highly recommended trying to understand
this.

Suppose that you have one node with 10 hosts assigned to a certain role.
Often these hosts will be managed completely independent. They are doing
exactly the same thing, but independent, just in parallel. No change on one
host will have any influence on the other hosts.  If you have such a situation,
deployment can be optimized, by running the same set of commands on every of
the 10 hosts in parallel.

The only thing you need to do, is tell the node which role contains the
hosts that can be isolated. This would be the role that contained the 10 hosts.
If any other role exists, 10 isolations will be created as well, but the other
roles will contain all the hosts like given, every time exactly the same.

```python
class database(Node):
    """
    roles = ('master', 'slaves')
    """
    @map_roles(host='slaves')
    class config_on_slaves(SimpleNode):
         def setup(self):
            """
            roles = ('host', )
            """
            pass
```

From the database class's point of view. `config_on_slaves` will now behave
like an array, instead of a single nodes. Calling `config_on_slaves.setup()`
would return an array of results. Because for every isolation (with their
host), the function will be executed once.


#### map_roles.just_one

Normally, when you are using host_isolation, the inner Node will behave like an
array from the point of view of the outer Node. However, sometimes, when you
are reusing nodes, you will get to a point where you are nesting two nodes
which are isolating on the same role. In that case, you're sure that there will
always be exactly one instance of the inner nodes, for every instance of the
outer nodes. The decorator `map_roles.just_one` will make sure that you don't
have to place `[0]` after accessing properties of the inner nodes.

Example:


```python
from deployer.node import SimpleNode

class MyRoot(SimpleNode):
    class inner_node(SimpleNode):
         property = value

         def setup(self):
             pass

    def setup(self):
        # This is not an array (it is when you drop the '.just_one')
        self.inner_node.property

        # This returns also not an array, but a single value.
        self.inner_node.setup()
```

#### `self.hosts` vs. `self.host`

Note that one is plural, the other is singular. In a node action,
`self.hosts` is a `HostsContainer` object. If you call `run` or `sudo` on this
object, the framework will run this command on every host in this container.
The container also has a `.filter(role)` function for reducing the set of hosts
in this container according to the role or roles you are passing.


The Q object
-------------------

The `Q` object is syntactic sugar for `@property`.

Suppose you have:

```python
class A(Node):
    @property
    def b(self):
        return self.c
```

No calculation is going on in the property, it's just a retrieval of another field.
You can write this as:

```python
class A(Node):
    b = Q.c
```


Some more sugar. This:
```python
class A(Node):
    @property
    def b(self):
        return self.parent.c[4].d % 'test'
```

can be written as:
```python
class A(Node):
    b = Q.parent.c[4].d % Q('test')
```


Using as a library
-------------------

This library was designed to be usable as a library. It does also not have a
global state, which makes it possible to use multiple independent node trees in
the same Python process.

...
