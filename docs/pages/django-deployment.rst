.. _django-tutorial:

Tutorial: Deploying a (Django) application
==========================================

This is a short tutorial that walks you through the steps required to create a
script that automatically installs a Django application on a server. We use the
Django application only as an example, the tutorial is meant to cover enough
that you can apply it yourself for deployments or management of any kind of
remote applications.

You learn how to write a deploy or remote execution script that can be
(re)used for installation of a new servers, for incremental upgrades or for
manually debugging the server.

Some assumptions:
 - You should have SSH credentials of the server on which you're going to
   deploy and you know how to use SSH.
 - You should know how to work with a bash shell.

Not required, but useful:
 - You have knowledge of Git, and your code is in a Git-repository. (Then we
   can use ``git clone`` to get our code on the servers.)
 - You have some knowledge of gunicorn, nginx and other tools for running wsgi
   applications.

.. note:: It's important that you understand the tools you're going to deploy,
          and how to cofigure them by hand. In this case, we are configuring gunicorn
          and Django as an example, so we would have to know how these things
          work. (You can't write a script to repeat some work for you, if you
          have no idea how to do it yourself.) The deployer framework has no
          idea what Django or nginx is, it just executes code on servers.

          This tutorial is only an example of how you could automatically
          deploy a Django application. You can but probably won't do it exactly
          as described here. The purpose of the tutorial is in the first place
          to explain some relevant steps, so you have an idea how you could
          create a repeatable script of the steps that you would otherwise do
          by hand.


So we are going to write a script that:
 - gets your code from the repository to the server (git clone);
 - Installs the requirements in a virtualenv;
 - sets up a ``local_settings.py`` configuration file on the server;
 - installs and configures Gunicorn.


Using python-deployer
---------------------

On your local system, you need to install the ``deployer`` Python library with
``pip`` or ``easy_install``.  (If you are not using a `virtualenv`_, you have
to use ``sudo`` to install it system-wide.)

.. _virtualenv: http://www.virtualenv.org/en/latest/

.. code-block:: bash

    pip install deployer

Now, you can create a new Python file, save it as ``deploy.py`` and paste the
following template in there.

::

    #!/usr/bin/env python
    from deployer.client import start
    from deployer.node import Node

    class DjangoDeployment(Node):
        pass

    if __name__ == '__main':
        start(DjangoDeployment)

Make it executable:

.. code-block:: bash

    chmod +x deploy.py

This does nothing yet. In the following sections, we are going to add more code
to the ``DjangoDeployment`` :class:`~deployer.node.base.Node`. If you run the
script, you will already get an :ref:`interactive shell <interactive-shell>`,
but there's also nothing much to see yet. Try to run the script as follows:

.. code-block:: bash

    ./deploy.py

You can quit the shell by typing ``exit``.

Writing the deployment script
-----------------------------

Git checkout
^^^^^^^^^^^^

Lets start by adding code for cloning and checking out a certain revision of
the repository. You can add the ``install_git``, ``git_clone`` and
``git_checkout`` methods in the snippet below to the ``DjangoDeployment`` node.

::

    from deployer.utils import esc1

    class DjangoDeployment(Node):
        project_directory = '~/git/django-project'
        repository = 'git@github.com:example/example.git'

        def install_git(self):
            """ Installs the ``git`` package. """
            self.host.sudo('apt-get install git')

        def git_clone(self):
            """ Clone repository."""
            with self.host.cd(self.project_directory, expand=True):
                self.host.run("git clone '%s'" % esc1(self.repository))

        def git_checkout(self, commit):
            """ Checkout specific commit (after cloning)."""
            with self.host.cd(self.project_directory, expand=True):
                self.host.run("git checkout '%s'" % esc1(commit))

Probably obvious, we have a clone and checkout function that are meant to go
to a certain directory on the server and run a shell command in there through
:func:`~deployer.host.base.Host.run`. Some points worth noting:

- ``expand=True``: this means that we should do tilde-expension. You want the
  tilde to be replaced with the home directory. If you have an absolute path,
  this isn't necessary.
- :func:`~deployer.utils.string_utils.esc1`: This is important to avoid shell
  injection. We receive the commit variable from a parameter, and we don't know
  what it will look like. The :func:`~deployer.utils.string_utils.esc1` escape
  function is designed to escape a string for use inside single quotes in a
  shell script: note the surrounding quotes in ``'%s'``.
- We need to use :func:`~deployer.host.base.Host.sudo` for the installation of
  Git, because ``apt-get`` needs to have root rights.


Defining the SSH host
^^^^^^^^^^^^^^^^^^^^^

Now we are going to define the SSH host. It is recommended to authenticate
through a private key. If you have a ``~/.ssh/config`` setup in a way that
allows you to connect directly through the ``ssh`` command by only passing the
address, then you also can drop all the other settings (except the address)
from the :class:`~deployer.host.ssh.SSHHost` below.

::

    from deployer.host import SSHHost

    class remote_host(SSHHost):
        address = '192.168.1.1' # Replace by your IP address
        username = 'user'       # Replace by your own username.
        password = 'password'   # Optional, but required for sudo operations
        key_filename = None     # Optional, specify the location of the RSA
                                #   private key


That defines how to access the remote host. If you ever have to define another
host, feel free to use Python inheritance if they share some settings.

Now we have to tell ``DjangoDeployment`` node to use this host. The following
syntax may look slightly overkill at first, but this is how we link the
``remote_host`` to the ``DjangoDeployment``. [#f1]_ Instead of putting the
``Hosts`` class inside the original ``DjangoDeployment``, you can off course
again --like always in Python-- inherit the original class and extend that one
by nesting ``Hosts`` in there.

::

    class DjangoDeployment(Node):
        class Hosts:
            host = remote_host

        ...

Put together, we currently have the following in our script:

::

    #!/usr/bin/env python
    from deployer.utils import esc1
    from deployer.host import SSHHost

    class remote_host(SSHHost):
        address = '192.168.1.1' # Replace by your IP address
        username = 'user'       # Replace by your own username.
        password = 'password'   # Optional, but required for sudo operations
        key_filename = None     # Optional, specify the location of the RSA
                                #   private key

    class DjangoDeployment(Node):
        class Hosts:
            host = remote_host

        project_directory = '~/git/django-project'
        repository = 'git@github.com:example/example.git'

        def install_git(self):
            """ Installs the ``git`` package. """
            self.host.sudo('apt-get install git')

        def git_clone(self):
            """ Clone repository."""
            with self.host.cd(self.project_directory, expand=True):
                self.host.run("git clone '%s'" % esc1(self.repository))

        def git_checkout(self, commit):
            """ Checkout specific commit (after cloning)."""
            with self.host.cd(self.project_directory, expand=True):
                self.host.run("git checkout '%s'" % esc1(commit))

    if __name__ == '__main':
        start(DjangoDeployment)


If you run this executable, you can already execute the methods if this class
from the interactive shell.

.. [#f1] The reason is that you can add multiple hosts to a node, and even
         multiple hosts to multiple 'roles' in a node. This allows for some
         more complex setups and parallel deployments.


Configuration management
^^^^^^^^^^^^^^^^^^^^^^^^

For most Django projects you also want to have a settings file for the server
configuration. Django projects define a Python module through the environment
variable `DJANGO_SETTINGS_MODULE`_. Usually, these settings are not entirely
the same on a local development machine and the server, you might have another
database or caching server. Often, you have a ``settings.py`` in your
repository, while each server still gets a ``local_settings.py`` to override
the server specific configurations. (`12factor.net`_ has some good guidelines
about config management.)

.. _DJANGO_SETTINGS_MODULE: https://docs.djangoproject.com/en/dev/topics/settings/#envvar-DJANGO_SETTINGS_MODULE
.. _12factor.net: http://12factor.net/ 

Anyway, suppose that you have a configuration that you want to upload to
``~/git/django-project/local_settings.py``. Let's create a method for that:

::

    django_settings = \
    """
    DATABASES['default'] = ...
    SESSION_ENGINE = ...
    DEFAULT_FILE_STORAGE = ...
    """

    class DjangoDeployment(Node):
        ...
        def upload_django_settings(self):
            """ Upload the content of the variable 'local_settings' in the
            local_settings.py file. """
            with self.host.open('~/git/django-project/local_settings.py') as f:
                f.write(django_settings)


So, by calling :func:`~deployer.host.base.Host.open`, we can write to a remote
file on the host, as if it were a local file.


Managing the virtualenv
^^^^^^^^^^^^^^^^^^^^^^^^

Virtualenvs can sometimes be very tricky to manage on the server and to use
them in automated scripts. You are working inside a virtualenv if your
``$PATH`` environment is set up to prefer binaries installed at the path of the
virtual env rather than use the system default. If you are working inside a
interactive shell, you may use a tool like ``workon`` or something similar to
activate the virtualenv. We don't want to rely on the availability of these
tools and inclusion of such scripts from a ``~/.bashrc``. Instead, we can call
the ``bin/activate`` by hand to set up a correct ``$PATH`` variable.  It is
important to prefix all commands that apply to the virtualenv by this
activation command.

In this tutorial we will suppose that you already have a virtualenv created by
hand, called ``'project-env'``.  Lets now create a few reusable functions for
installing stuff inside the virtualenv.

.. code-block:: python

    class DjangoDeployment(Node):
        ...
        # Command to execute to work on the virtualenv
        activate_cmd = '. ~/.virtualenvs/project-env/bin/activate'

        def install_requirements(self):
            """
            Script to install the requirements of our Django application.
            (We have a requirements.txt file in our repository.)
            """
            with self.host.prefix(self.activate_cmd):
                self.host.run("pip install -r ~/git/django-project/requirements.txt")

        def install_package(self, name):
            """
            Utility for installing packages through ``pip install`` inside
            the env.
            """
            with self.host.prefix(self.activate_cmd):
                self.host.run("pip install '%s'" % name)

Notice the :func:`~deployer.host.base.HostContext.prefix` context manager that
makes sure that all :func:`~deployer.host.base.Host.run` commands are executed
inside the virtualenv.

Running Django management commands
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

It's good and useful have to have a helper function somewhere that can execute
Django management commands from the deployment script. You're going to use it
all the time. 

Lets add a ``run_management_command`` which accepts a ``command`` parameter to
be passed as an argument to ``./manage.py``. As an example we also add a
``django_shell`` method which starts in interactive django shell on the server.

.. code-block:: python

    class DjangoDeployment(Node):
        ...
        def run_management_command(self, command):
            """ Run Django management command in virtualenv. """
            # Activate the virtualenv.
            with self.host.prefix(self.activate_cmd):
                # Go to the directory where we have our 'manage.py' file.
                with self.host.cd('~/git/django-project/'):
                    self.host.run('./manage.py %s' % command)

        def django_shell(self):
            """ Open interactive Django shell. """
            self.run_management_command('shell')

Running gunicorn through supervisord
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You don't want to use Django's ``runserver`` on production, so we're going to
install and configure `gunicorn`_. We are going to use `supervisord`_ to
mangage the gunicorn process, but depending on your system you meight prefer
`systemd`_ or `upstart`_ instead. We need to install both gunicorn and
supervisord in the environment and create configuration files file both.

.. _gunicorn: http://gunicorn.org/
.. _supervisord: http://supervisord.org/
.. _systemd: http://en.wikipedia.org/wiki/Systemd
.. _upstart: http://upstart.ubuntu.com/

Let's first add a few methods for installing the required packages inside the
virtualenv.

.. code-block:: python

    class DjangoDeployment(Node):
        ...

        def install_gunicorn(self):
            """ Install gunicorn inside the virtualenv. """
            self.install_package('gunicorn')

        def install_supervisord(self):
            """ Install supervisord inside the virtualenv. """
            self.install_package('supervisor')

For testing purposes, we add a command to run the gunicorn server from the
shell. [#f2]_

.. code-block:: python

    class DjangoDeployment(Node):
        ...

        def run_gunicorn(self):
            """ Run the gunicorn server """
            self.run_management_command('run_gunicorn')

Obviously, you don't want to keep your shell open all the time. So, let's
configure supervisord. The following code will upload the supervisord
configuration to ``/etc/supervisor/conf.d/django-project.conf``. This is
similar to uploading the Django configuration earlier.

.. code-block:: python

    supervisor_config = \
    """
    [program:djangoproject]
    command = /home/username/.virtualenvs/project-env/bin/gunicorn_start  ; Command to start app
    user = username                                                       ; User to run as
    stdout_logfile = /home/username/logs/gunicorn_supervisor.log          ; Where to write log messages
    redirect_stderr = true                                                ; Save stderr in the same log
    """

    class DjangoDeployment(Node):
        ...

        def upload_supervisor_config(self):
            """ Upload the content of the variable 'supervisor_config' in the
            supervisord configuration file. """
            with self.host.open('/etc/supervisor/conf.d/django-project.conf') as f:
                f.write(supervisor_config)


Gathering again everything we have:

.. code-block:: python

    #!/usr/bin/env python
    from deployer.utils import esc1
    from deployer.host import SSHHost

    supervisor_config = \
    """
    [program:djangoproject]
    command = /home/username/.virtualenvs/project-env/bin/gunicorn_start  ; Command to start app
    user = username                                                       ; User to run as
    stdout_logfile = /home/username/logs/gunicorn_supervisor.log          ; Where to write log messages
    redirect_stderr = true                                                ; Save stderr in the same log
    """

    django_settings = \
    """
    DATABASES['default'] = ...
    SESSION_ENGINE = ...
    DEFAULT_FILE_STORAGE = ...
    """

    class remote_host(SSHHost):
        address = '192.168.1.1' # Replace by your IP address
        username = 'user'       # Replace by your own username.
        password = 'password'   # Optional, but required for sudo operations
        key_filename = None     # Optional, specify the location of the RSA
                                #   private key
    class DjangoDeployment(Node):
        class Hosts:
            host = remote_host

        project_directory = '~/git/django-project'
        repository = 'git@github.com:example/example.git'

        def install_git(self):
            """ Installs the ``git`` package. """
            self.host.sudo('apt-get install git')

        def git_clone(self):
            """ Clone repository."""
            with self.host.cd(self.project_directory, expand=True):
                self.host.run("git clone '%s'" % esc1(self.repository))

        def git_checkout(self, commit):
            """ Checkout specific commit (after cloning)."""
            with self.host.cd('~/git/django-project', expand=True):
                self.host.run("git checkout '%s'" % esc1(commit))

        # Command to execute to work on the virtualenv
        activate_cmd = '. ~/.virtualenvs/project-env/bin/activate'

        def install_requirements(self):
            """
            Script to install the requirements of our Django application.
            (We have a requirements.txt file in our repository.)
            """
            with self.host.prefix(self.activate_cmd):
                self.host.run("pip install -r ~/git/django-project/requirements.txt")

        def install_package(self, name):
            """
            Utility for installing packages through ``pip install`` inside
            the env.
            """
            with self.host.prefix(self.activate_cmd):
                self.host.run("pip install '%s'" % name)

        def upload_django_settings(self):
            """ Upload the content of the variable 'local_settings' in the
            local_settings.py file. """
            with self.host.open('~/git/django-project/local_settings.py') as f:
                f.write(django_settings)

        def run_management_command(self, command):
            """ Run Django management command in virtualenv. """
            # Activate the virtualenv.
            with self.host.prefix(self.activate_cmd):
                # Cd to the place where we have our 'manage.py' file.
                with self.host.cd('~/git/django-project/'):
                    self.host.run('./manage.py %s' % command)

        def django_shell(self):
            """ Open interactive Django shell. """
            self.run_management_command('shell')

        def install_gunicorn(self):
            """ Install gunicorn inside the virtualenv. """
            self.install_package('gunicorn')

        def install_supervisord(self):
            """ Install supervisord inside the virtualenv. """
            self.install_package('supervisor')

        def run_gunicorn(self):
            """ Run the gunicorn server """
            self.run_management_command('run_gunicorn')

        def upload_supervisor_config(self):
            """ Upload the content of the variable 'supervisor_config' in the
            supervisord configuration file. """
            with self.host.open('/etc/supervisor/conf.d/django-project.conf') as f:
                f.write(supervisor_config)

    if __name__ == '__main':
        start(DjangoDeployment)

.. [#f2] See: http://docs.gunicorn.org/en/latest/run.html#django-manage-py


Making stuff reusable
---------------------

The above deployment script works. But it's not really reusable. You don't want
to write a gunicorn configuration for every Django project you're going to set
up. And you also don't want to do the same again for a staging environment if
you have the scripts for the production, even when there are minor differences.
So we are going to move hard coded parts out of our code and make our
``DjangoDeployment`` reusable.

A reusable virtualenv class.
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Let's start by putting all the virtualenv related functions in one class. Most
of the script will be the same among projects, except for a few variables:
 - The location of the virtualenv
 - The packages to be installed there
 - The location of a ``requirements.txt`` file

 A reusable ``VirtualEnv`` class could look like this:

.. code-block:: python

    class VirtualEnv(Node):
        location = required_property()
        requirements_files = []
        packages = []

        # Command to execute to work on the virtualenv
        @property
        def activate_cmd(self):
            return  '. %s/bin/activate' % self.location

        def install_requirements(self):
            """
            Script to install the requirements of our Django application.
            (We have a requirements.txt file in our repository.)
            """
            with self.host.prefix(self.activate_cmd):
                for f in self.requirements_files:
                    self.host.run("pip install -r '%s' " % esc1(f))

        def install_package(self, name):
            """
            Utility for installing packages through ``pip install`` inside
            the env.
            """
            with self.host.prefix(self.activate_cmd):
                self.host.run("pip install '%s'" % name)

        def setup_env(self):
            """ Install everything inside the virtualenv """
            # From `self.packages`
            for p in self.packages:
                self.install_package(p)

            # From requirements.txt files
            self.install_requirements()

So we have created another :class:`~deployer.node.Node` class and moved some of
the code we already had in there. The ``setup_env`` method is added to group
the installation in one command. One other thing worth noting is the
``location`` class variable, to which :func:`~deployer.node.required_property`
was assigned. Actually, that is a property that raises an exception when it's
accessed. The idea there is that we inherit from the ``VirtualEnv`` class and
override this variable by an actual value.

Now, to use this in the ``DjangoDeployment`` node is now possible by nesting
these classes. As said, we inherit from ``VirtualEnv`` and replace the
variables by whatever we need. We also add a ``setup`` method in
``DjangoDeployment`` which will eventually do all the setup, so that we only
have to call one method for the first initial setup of our deployment.

.. code-block:: python

    class DjangoDeployment(Node):
        ...

        class virtual_env(VirtualEnv):
            location = '~/.virtualenvs/project-env/'
            requirements_files = [ '~/git/django-project/requirements.txt' ]
            packages = [ 'gunicorn', 'supervisor' ] 

        def setup(self):
            # Install virtual packages
            self.virtual_env.setup_env()

        ...

Did you see what we did? This ``setup``-method does some magic. Take a look at
how we access ``virtual_env``. Normal Python code would return a ``VirtualEnv``
class at that point, so ``self.virtual_env.setup_env`` would be a classmethod
and you would get a ``TypeError: unbound method must be called with ...``
exception. But in a ``Node`` class, Python acts differently, if we access one
node class which is nested inside another, we'll automatically get a ``Node``
instance of the inner class. [#f3]_

The reason will probably become clearer if you take a look The ``self.host``
variable. Calling run on ``self.host`` will execute commands on that host.
Remember that we defined the host by nesting the ``Hosts`` class inside the
``DjangoDeployment`` node? We didn't have to do that for ``virtual_env``, but
``VirtualEnv`` also expects ``self.host.run`` to work. The magic is what we
call mapping of roles/hosts. If not explicitely defined, an instance of the
nested class knows on which hosts to execute by looking at the parent instance,
and they're linked because the framework instantiates the nested class at the
point that we access from the parent.

You should not worry too much about what happens under the hood, it's a well
tested and well thought through, but it can be hard to grasp at first.

.. [#f3] Internally, this works thanks to Python descriptors.


Reusable ``git`` class
^^^^^^^^^^^^^^^^^^^^^^

Let's do something similar for the ``git`` class.

.. code-block:: python

    class Git(Node):
        project_directory = required_property()
        repository = required_property()

        def install(self):
            """ Installs the ``git`` package. """
            self.host.sudo('apt-get install git')

        def clone(self):
            """ Clone repository."""
            with self.host.cd(self.project_directory, expand=True):
                self.host.run("git clone '%s'" % esc1(self.repository))

        def checkout(self, commit):
            """ Checkout specific commit (after cloning)."""
            with self.host.cd('~/git/django-project', expand=True):
                self.host.run("git checkout '%s'" % esc1(commit))

And in ``DjangoDeployment``:

.. code-block:: python

    class DjangoDeployment(Node):
        ...

        class git(Git):
            project_directory = '~/git/django-project'
            repository = 'git@github.com:example/example.git'

        def setup(self):
            # Clone repository
            self.git.clone()

            # Install virtual packages
            self.virtual_env.setup_env()


Our reusable ``DjangoDeployment``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If we do the same exercise for the other parts of our script we get the
following. The ``Hosts`` class is removed by purpose, the reason will become
clear in the following section.

Let's save the following in a file called ``django_deployment.py``:

.. code-block:: python

    from deployer.utils import esc1
    from deployer.host import SSHHost

    supervisor_config = \
    """
    [program:djangoproject]
    command = /home/username/.virtualenvs/project-env/bin/gunicorn_start  ; Command to start app
    user = username                                                       ; User to run as
    stdout_logfile = /home/username/logs/gunicorn_supervisor.log          ; Where to write log messages
    redirect_stderr = true                                                ; Save stderr in the same log
    """

    django_settings = \
    """
    DATABASES['default'] = ...
    SESSION_ENGINE = ...
    DEFAULT_FILE_STORAGE = ...
    """

    class VirtualEnv(Node):
        location = required_property()
        requirements_files = []
        packages = []

        # Command to execute to work on the virtualenv
        @property
        def activate_cmd(self):
            return  '. %s/bin/activate' % self.location

        def install_requirements(self):
            """
            Script to install the requirements of our Django application.
            (We have a requirements.txt file in our repository.)
            """
            with self.host.prefix(self.activate_cmd):
                for f in self.requirements_files:
                    self.host.run("pip install -r '%s' " % esc1(f))

        def install_package(self, name):
            """
            Utility for installing packages through ``pip install`` inside
            the env.
            """
            with self.host.prefix(self.activate_cmd):
                self.host.run("pip install '%s'" % name)

        def setup_env(self):
            """ Install everything inside the virtualenv """
            # From `self.packages`
            for p in self.packages:
                self.install_package(p)

            # From requirements.txt files
            self.install_requirements()

    class Git(Node):
        project_directory = required_property()
        repository = required_property()

        def install(self):
            """ Installs the ``git`` package. """
            self.host.sudo('apt-get install git')

        def clone(self):
            """ Clone repository."""
            with self.host.cd(self.project_directory, expand=True):
                self.host.run("git clone '%s'" % esc1(self.repository))

        def checkout(self, commit):
            """ Checkout specific commit (after cloning)."""
            with self.host.cd('~/git/django-project', expand=True):
                self.host.run("git checkout '%s'" % esc1(commit))

    class DjangoDeployment(Node):
        class virtual_env(VirtualEnv):
            location = '~/.virtualenvs/project-env/'
            packages = [ 'gunicorn', 'supervisor' ] 
            requirements_files = ['~/git/django-project/requirements.txt' ]

        class git(Git):
            project_directory = '~/git/django-project'
            repository = 'git@github.com:example/example.git'

        def setup(self):
            # Clone repository
            self.git.clone()

            # Install virtual packages
            self.virtual_env.setup_env()

        def upload_django_settings(self):
            """ Upload the content of the variable 'local_settings' in the
            local_settings.py file. """
            with self.host.open('~/git/django-project/local_settings.py') as f:
                f.write(django_settings)

        def run_management_command(self, command):
            """ Run Django management command in virtualenv. """
            # Activate the virtualenv.
            with self.host.prefix(self.activate_cmd):
                # Cd to the place where we have our 'manage.py' file.
                with self.host.cd('~/git/django-project/'):
                    self.host.run('./manage.py %s' % command)

        def django_shell(self):
            """ Open interactive Django shell. """
            self.run_management_command('shell')

        def run_gunicorn(self):
            """ Run the gunicorn server """
            self.run_management_command('run_gunicorn')

        def upload_supervisor_config(self):
            """ Upload the content of the variable 'supervisor_config' in the
            supervisord configuration file. """
            with self.host.open('/etc/supervisor/conf.d/django-project.conf') as f:
                f.write(supervisor_config)


Adding hosts
^^^^^^^^^^^^

The file that we saved to ``django_deployment.py`` in the previous section did
not contain any hosts. So, it's rathar a template of a deployment script that
we are going to apply here on a host. We inherit from ``DjangoDeployment`` and
add the hosts.

.. code-block:: python

    #!/usr/bin/env python

    class remote_host(SSHHost):
        address = '192.168.1.1' # Replace by your IP address
        username = 'user'       # Replace by your own username.
        password = 'password'   # Optional, but required for sudo operations
        key_filename = None     # Optional, specify the location of the RSA
                                #   private key
    class DjangoDeploymentOnHost(DjangoDeployment):
        class Hosts:
            host = remote_host

        # Override a few properties of the parent.
        virtual_env__location = '~/.virtualenvs/project-env-2/' 
        git__project_directory = '~/git/django-project-2' 

    if __name__ == '__main':
        start(DjangoDeploymentOnHost)

Class inheritance is powerful in Python. But did you notice the that we never
had a ``git__project_directory`` or ``virtual_env__location`` variable before?
This is again some magic. It's a pattern that very offen occurs in this
framework. Python has no easy way to write that you want to override a property
of the nested class. We introduced :ref:`double underscore expansion
<double-underscore-expansion>` which tells Python that in our case that if a
member of a node class has double underscores in its name, it means that we are
overriding a property of a nested node. In this case we override the
``location`` property of the ``virtual_env`` class of the parent and the value
of ``project_directory`` of the nested ``git`` class.

That's it. This script is executable and if you start it, you have a nice
interactive shell from which you can run all the commands.

And now?
--------

The script can still even more be improved. For instance, in
``deployer.contrib.nodes.config`` is a nice ``Config`` class that we could use
for managing the Django and supervisord settings. It contains a few handy
functions for comparing the content of the remote file with that of what we
would overwrite it with.


Also, learn about :ref:`query expressions <query-expressions>` and the
:attr:`~deployer.node.base.Node.parent` variable which are very powerful.
