from deployer.console import input
from deployer.contrib.services.apt_get import AptGet
from deployer.contrib.services.uwsgi import Uwsgi
from deployer.query import Q
from deployer.service import Service, isolate_host, ServiceBase, map_roles, supress_action_result, required_property, isolate_one_only, alias
from deployer.utils import esc1
from functools import wraps

import os


wsgi_app_template = \
"""
import os
import sys

import django.core.handlers.wsgi


# redirect stdout
null = open(os.devnull, 'w')
sys.stdout = null

# specify the settings
os.environ['DJANGO_SETTINGS_MODULE'] = '%(settings_module)s'

# Since we want to parse some HTTP headers (for https support), we don't create
# the WSGI handler as `application`.
_application = django.core.handlers.wsgi.WSGIHandler()


def application(environ, start_response):
    # trick Django into thinking proxied traffic is coming in via HTTPS
    # HTTP_X_FORWARDED_SSL is used on WebFaction
    if environ.get('HTTP_X_FORWARDED_PROTOCOL', 'http') == 'https' or \
       environ.get('HTTP_X_FORWARDED_SSL', 'off') == 'on':
        environ['wsgi.url_scheme'] = 'https'
    return _application(environ, start_response)
"""


class DjangoBase(ServiceBase):
    _default_commands = {
        'clean_pyc': 'clean_pyc',
        'dbshell': 'dbshell',
        'help': 'help',
        'list_migrations': 'migrate --list',
        'migrate': 'migrate --noinput --no-initial-data --merge --ignore-ghost-migrations',
        'runserver': lambda self: 'runserver 0.0.0.0:%i' % self.runserver_port,
        'shell': 'shell',
        'shell_plus': 'shell_plus',
        'syncdb': 'syncdb --noinput',
    }
    _on_every_host = ['clean_pyc', 'runserver' ] # These are run on every host.

    def __new__(cls, name, bases, attrs):
        # Give this Django class management commands, based on the
        # commands dictionary
        commands = attrs.get('commands', { })

        # Default commands
        for cmd_name, command in cls._default_commands.items():
            attrs[cmd_name] = cls._create_task(cmd_name, command,
                                    one_only=(command not in cls._on_every_host))

        # Custom additional commands
        for cmd_name, command in commands.items():
            attrs[cmd_name] = cls._create_task(cmd_name, command)

        return ServiceBase.__new__(cls, name, bases, attrs)

    @staticmethod
    def _create_task(name, task, one_only=True):
        """
        Take the first host, 'cd' to the django project.
        And run this django command using the correct settings module.
        """
        @supress_action_result
        def command(self):
            # Take only the first host. Assume that if we have multiple hosts,
            # they all connect to the same database. So, there's no point in
            # running this command on every host.
            host = self.hosts[0]

            parent_directory, dir2 = self.django_project.rstrip('/').rsplit('/', 1)

            with host.cd(parent_directory):
                with host.env('term', 'xterm'):
                    task2 = task(self) if callable(task) else task
                    return host.run('%s/bin/python %s/manage.py %s --settings=%s' % (
                            self.virtual_env_location, dir2, task2, self.settings_module))

        # For most of the commands, it's sufficient, to run on only one host.
        # It does for instance not make any sence to open 10 shell_plus
        # instances, if we have 10 django instances with the same database
        # backend.
        if one_only:
            command = isolate_one_only(command)

        command.__name__ = (task if isinstance(task, basestring) else name)
        return command


@isolate_host
class Django(Service):
    __metaclass__ = DjangoBase

    # Location of the virtual env
    virtual_env_location = ''

    # Django project location. This is the directory which contains the
    # manage.py file.
    django_project = ''

    # Django commands (mapping from command name, to ./manage.py parameter)
    commands = { }

    # User for the upstart service
    username = required_property()
    slug = 'default-django-app'
    uwsgi_socket = 'localhost:3032' # Can be either a tcp socket or unix file socket
    uwsgi_threads = 10
    uwsgi_workers = 2

    runserver_port = 8000

    def _get_management_command(self, command):
        """
        Create the call for a management command.
        (For use in cronjobs, etc...)
        NOTE: The command itself is not shell-escaped, be sure to use proper quoting
              if necessary!
        """
        parent_directory, dir2 = self.django_project.rsplit('/', 1)
        return "cd '%s'; '%s/bin/python' '%s/manage.py' %s" % (
                    parent_directory, self.virtual_env_location, dir2, command)

    def _run_management_command(self, command):
        self.hosts.run(self._get_management_command(command))

    @isolate_one_only
    @alias('manage.py')
    def _manage_py(self, command=None):
        command = command or input('python manage.py (...)')
        self._run_management_command(command)

    @property
    def settings_module(self):
        return self.django_project.rstrip('/').rsplit('/', 1)[-1] + '.settings'

    @property
    def wsgi_app_location(self):
        return '/etc/wsgi-apps/%s.py' % self.slug


    # ===========[ WSGI setup ]============

    @map_roles.just_one
    class uwsgi(Uwsgi):
        uwsgi_socket = Q.parent.uwsgi_socket
        slug = Q.parent.slug
        wsgi_app_location = Q.parent.wsgi_app_location
        uwsgi_threads = Q.parent.uwsgi_threads
        uwsgi_workers = Q.parent.uwsgi_workers
        virtual_env_location = Q.parent.virtual_env_location
        username = Q.parent.username

        @property
        def run_from_directory(self):
            return self.parent.django_project + '/..'

        def setup(self):
            Uwsgi.setup(self)
            self.parent.install_wsgi_app()


    def install_wsgi_app(self):
        """
        Install wsgi script for this django application
        """
        for h in self.hosts:
            h.sudo("mkdir -p $(dirname '%s')" % self.wsgi_app_location)
            h.open(self.wsgi_app_location, 'wb', use_sudo=True).write(wsgi_app_template % { 'settings_module': self.settings_module })
            h.sudo("chown %s '%s'" % (self.username, self.wsgi_app_location))
