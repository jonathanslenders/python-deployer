.. _django-tutorial:

Tutorial: deploying a Django application
========================================

This is a short tutorial that walks you through the steps required to create a
script that automatically installs a Django application on a server. It will be
reusable in a way that it can be reused for installation of a new server or an
incremental upgrade of the application.

Some assumptions:
 - You should have SSH credentials of the server on which you're going to deploy.
 - Your code should be in a Git repository. (the tutorial uses Git, but it
   applies as well for any source control system that you can check out on the
   server.)
 - You know how to work with a bash shell and you have some knowledge of
   gunicorn, nginx and other tools for running wsgi applications.

.. note:: This tutorial is only an example of how you could automatically
          deploy a Django application. You can but probably won't do it exactly
          like described here. The purpose of the tutorial is in the first
          place to explain some relevant steps, so you have an idea how you
          could create a repeatable script of the steps that you would
          otherwise do by hand.

          So, it's still important to understand how nginx/apache,
          gunicorn/uwsgi and other tools work and how to configure them by
          hand. (You can't write a script to repeat some work for you, if you
          have no idea how to do it yourself.)

Intro
-----

So we are going to write a script that:
 - gets your code from the repository to the server (git clone);
 - creates a virtualenv and installs all the requirements in there;
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

This does nothing yet, we are going to add more code in the
``DjangoDeployment`` node in the following sections. If you run the script, you
will already get an interactive shell, but there's also nothing much to see
yet. Try to run the script as follows:

.. code-block:: bash

    ./deploy.py

You can quit the shell by typing ``exit``.

Writing the deployment script
-----------------------------

Git checkout
^^^^^^^^^^^^

Lets start by adding code for cloning and checking out a certain revision of
the repository. I suppose you know how ``git clone`` and ``git checkout`` work.
You can add the ``git_clone`` and ``git_checkout`` methods in the snippet below
to the ``DjangoDeployment`` node.

::

    from deployer.utils import esc1

    class DjangoDeployment(Node):
        ...
        project_directory = '~/git/django-project'

        def git_clone(self):
            """ Clone repository."""
            with self.host.cd(self.project_directory, expand=True):
                self.host.run('git clone git@github.com:example/example.git')

        def git_checkout(self, commit):
            """ Checkout specific commit (after cloning)."""
            with self.host.cd(self.project_directory, expand=True):
                self.host.run("git checkout '%s'" % esc1(commit))

Probably obvious, we have a clone and checkout function that are meant to move
to a certain directory on the server and run a shell command in there. Some
points worth noting:

- ``expand=True``: this means that we should do tilde-expension. You want the
  tilde to be replaced with the home directory. If you have an absolute path,
  this isn't necessary.
- :func:`~deployer.utils.string_utils.esc1`: This is important to avoid shell
  injection. We receive the commit variable from a parameter, and we don't know
  what it will look like. The :func:`~deployer.utils.string_utils.esc1` escape
  function is designed to escape a string for use inside single quotes in a
  shell script: note the surrounding quotes in ``'%s'``.

Adding the SSH host
^^^^^^^^^^^^^^^^^^^

Now we are going to define the real SSH host. It is recommended to authenticate
through a private key. If you have ``~/.ssh/config`` setup in a way that allows
you to connect directly through the ``ssh`` command by only passing the
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


That defines how to access the remote host, but we still have to link it to the
``DjangoDeployment`` node. The following syntax may look slightly overkill at
first, but this is how to link it the ``DjangoDeployment`` node to
``remote_host``. [#f1]_ Instead of putting the ``Hosts`` class inside
the original ``DjangoDeployment``, you can off course --like always in Python--
inherit the original class and extend that one by nesting ``Hosts`` in there.

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

        def git_clone(self):
            """ Clone repository."""
            with self.host.cd(self.project_directory, expand=True):
                self.host.run('git clone git@github.com:example/example.git')

        def git_checkout(self, commit):
            """ Checkout specific commit (after cloning)."""
            with self.host.cd(self.project_directory, expand=True):
                self.host.run("git checkout '%s'" % esc1(commit))

    if __name__ == '__main':
        start(DjangoDeployment)

.. [#f1] The reason is that you can add multiple hosts to a node, and even
         multiple hosts to multiple 'roles' to a node. This allows for some
         more complex setups and parallel deployments.

Configuration management
^^^^^^^^^^^^^^^^^^^^^^^^

For most Django projects you also want to have a settings file on the server
configuration. Django projects define a Python module through the environment
variable `DJANGO_SETTINGS_MODULE`_. Usually, these settings are not entirely
the same on a local development machine and the server, you might have another
database or caching server. Typically, you have a ``settings.py`` in your
repository, while each server still gets a ``local_settings.py`` to override
the server specific configurations. (`12factor.net`_ has some good
guidelines about config management.)

.. _DJANGO_SETTINGS_MODULE: https://docs.djangoproject.com/en/dev/topics/settings/#envvar-DJANGO_SETTINGS_MODULE
.. _12factor.net: http://12factor.net/ 

Anyway, suppose that you have a configuration that you want to upload to
``~/git/django-project/local_settings.py``. Let's create a method for that:

::

    local_django_settings = \
    """
    DATABASES['default'] = ...
    SESSION_ENGINE = ...
    DEFAULT_FILE_STORAGE = ...
    """

    class DjangoDeployment(Node):
        def upload_django_settings(self):
            """ Upload the content of the variable 'local_settings' in the
            local_settings.py file. """
            with self.host.open('~/git/django-project/local_settings.py') as f:
                f.write(local_django_settings)


So, by calling :func:`~deployer.host.base.Host.open`, we can write to a remote
file on the host, as if it were a local file.


Managing the virtualenv
^^^^^^^^^^^^^^^^^^^^^^^^

Virtualenvs can sometimes be very tricky to manage them on the server and to
use them in automated scripts. You are working inside a virtualenv if your
``$PATH`` environment is set up to prefer binaries installed at the path of the
virtual env rather than use the system default. If you are working inside a
interactive shell, you may use a tool like ``workon`` or something similar to
activate the virtualenv. We don't want to rely on the availability of these
tools and inclusion of such scripts from a ``~/.bashrc``, but instead, we can
call the ``bin/activate`` by hand to set up a correct ``$PATH`` variable.  It
is important to prefix all commands that apply to the virtualenv by this
activation command.

In this tutorial we will suppose that you already have a virtualenv created by
hand, called ``'project-env'``.  Lets now create a few reusable functions for
installing stuff inside the virtualenv.

.. code-block:: python

    class DjangoDeployment(Node):
        ...
        class VirtualEnv(Node):
            # Command to execute to work on the virtualenv
            activate_cmd = '. ~/.virtualenvs/project-env/bin/activate'

            def install_requirements(self):
                """
                Script to install the requirements of our Django application.
                (We have a requirements.txt file in our repository.)
                """
                with self.host.prefix(self.activate_cmd):
                    self.host.run("pip install -r ~/git/django-project/requirements.txt')

            def install_package(self, name):
                """
                Utility for installing packages through ``pip install`` inside
                the env.
                """
                with self.host.prefix(self.activate_cmd):
                    self.host.run("pip install '%s'" % name)

Notice the :func:`~deployer.host.base.Host.prefix` context manager that makes
sure that all :func:`~deployer.host.base.Host.run` commands are executed inside
the virtualenv.

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
            with self.host.prefix(self.VirtualEnv.activate_cmd):
                # Cd to the place where we have our 'manage.py' file.
                with self.host.cd('~/git/django-project/'):
                    self.host.run('./manage.py %s' % command)

        def django_shell(self):
            """ Open interactive Django shell. """
            self.run_management_command('shell')

Running gunicorn through upstart
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You don't want to use Django's ``runserver`` on production, so we're going to
install and configure `gunicorn`_. We are going to use `supervisord`_ to
mangage the gunicorn process, but depending on your system you meight prefer
`systemd`_ or `upstart`_ instead. We need to create install both gunicorn and
supervisord in the environment and create configuration files file both.

.. _gunicorn: http://gunicorn.org/
.. _supervisord: http://supervisord.org/
.. _systemd: http://en.wikipedia.org/wiki/Systemd
.. _upstart: http://upstart.ubuntu.com/

Let's first add a few methods for installing the required packages inside the
virtualenv. See how we can use the nested class ``VirtualEnv`` as a variable
here, and use the install_package function from there.

.. code-block:: python

    class DjangoDeployment(Node):
        ...

        def install_gunicorn(self):
            """ Install gunicorn inside the virtualenv. """
            self.VirtualEnv.install_package('gunicorn')

        def install_supervisord(self):
            """ Install supervisord inside the virtualenv. """
            self.VirtualEnv.install_package('supervisord')

For testing purposes, we add a command to run the gunicorn server from the
shell. [#f2]_

.. [#f2] See: http://docs.gunicorn.org/en/latest/run.html#django-manage-py

.. code-block:: python

    class DjangoDeployment(Node):
        ...

        def run_gunicorn(self):
            """ Run the gunicorn server """
            self.run_management_command('run_gunicorn')

Obviously, you don't want to keep your shell open all the time. So, let's
configure supervisord. The following code will upload the supervisord
configuration to ``/etc/supervisor/conf.d/django-project.conf``:

.. #TODO: Add setup()-method.

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


Gathering again everything, we have:

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

    local_django_settings = \
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

        def git_clone(self):
            """ Clone repository."""
            with self.host.cd('~/git/django-project', expand=True):
                self.host.run('git clone git@github.com:example/example.git')

        def git_checkout(self, commit):
            """ Checkout specific commit (after cloning)."""
            with self.host.cd('~/git/django-project', expand=True):
                self.host.run("git checkout '%s'" % esc1(commit))

        class VirtualEnv(Node):
            # Command to execute to work on the virtualenv
            activate_cmd = '. ~/.virtualenvs/project-env/bin/activate'

            def install_requirements(self):
                """
                Script to install the requirements of our Django application.
                (We have a requirements.txt file in our repository.)
                """
                with self.host.prefix(self.activate_cmd):
                    self.host.run("pip install -r ~/git/django-project/requirements.txt')

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
                f.write(local_django_settings)

        def run_management_command(self, command):
            """ Run Django management command in virtualenv. """
            # Activate the virtualenv.
            with self.host.prefix(self.VirtualEnv.activate_cmd):
                # Cd to the place where we have our 'manage.py' file.
                with self.host.cd('~/git/django-project/'):
                    self.host.run('./manage.py %s' % command)

        def django_shell(self):
            """ Open interactive Django shell. """
            self.run_management_command('shell')

        def install_gunicorn(self):
            """ Install gunicorn inside the virtualenv. """
            self.VirtualEnv.install_package('gunicorn')

        def install_supervisord(self):
            """ Install supervisord inside the virtualenv. """
            self.VirtualEnv.install_package('supervisord')

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

Restructuring the script: making stuff reusable
-----------------------------------------------

Removing the hard-coded pieces
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^


Using configuration classes
^^^^^^^^^^^^^^^^^^^^^^^^^^^



