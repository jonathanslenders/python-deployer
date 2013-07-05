from deployer.contrib.nodes.uwsgi import Uwsgi
from deployer.query import Q
from deployer.node import SimpleNode, SimpleNodeBase, suppress_action_result, required_property, isolate_one_only, alias
from deployer.contrib.nodes.config import Config


wsgi_app_template = \
"""
import os
import sys

import django.core.handlers.wsgi


# redirect stdout
null = open(os.devnull, 'w')
sys.stdout = null

# specify the settings
os.environ['DJANGO_SETTINGS_MODULE'] = %(settings_module)s

if %(auto_reload)s:
    import uwsgi
    from uwsgidecorators import timer
    from django.utils import autoreload

    @timer(3)
    def change_code_gracefull_reload(sig):
        if autoreload.code_changed():
            uwsgi.reload()



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


class DjangoBase(SimpleNodeBase):
    _default_commands = {
        'clean_pyc': 'clean_pyc',
        'dbshell': 'dbshell',
        'help': 'help',
        'list_migrations': 'migrate --list',
        'migrate': 'migrate --noinput --no-initial-data --merge --ignore-ghost-migrations',
        'runserver': lambda self: 'runserver 0.0.0.0:%i' % self.http_port,
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

        return SimpleNodeBase.__new__(cls, name, bases, attrs)

    @staticmethod
    def _create_task(name, task, one_only=True):
        """
        Take the first host, 'cd' to the django project.
        And run this django command using the correct settings module.
        """
        @suppress_action_result
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


class Django(SimpleNode):
    __metaclass__ = DjangoBase

    # Location of the virtual env
    virtual_env_location = required_property()

    # Django project location. This is the directory which contains the
    # manage.py file.
    django_project = required_property()

    # Django commands (mapping from command name, to ./manage.py parameter)
    commands = { }

    # User for the upstart service
    username = required_property()
    slug = 'default-django-app'

    # HTTP Server
    http_port = 8000

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
        command = command or self.console.input('python manage.py (...)')
        self._run_management_command(command)

    @property
    def settings_module(self):
        return self.django_project.rstrip('/').rsplit('/', 1)[-1] + '.settings'


    # ===========[ WSGI setup ]============

    class uwsgi(Uwsgi):
        slug = Q.parent.slug
        wsgi_app_location = Q.parent.wsgi_app.remote_path
        virtual_env_location = Q.parent.virtual_env_location
        username = Q.parent.username

        use_http = True
        wsgi_module = Q('%s_wsgi:application') % Q.parent.slug

        @property
        def run_from_directory(self):
            return self.parent.django_project + '/..'

        def setup(self):
            Uwsgi.setup(self)
            self.parent.wsgi_app.setup()

    class wsgi_app(Config):
        remote_path = Q("%s/%s_wsgi.py") % (Q.parent.uwsgi.run_from_directory, Q.parent.slug)
        auto_reload = False

        @property
        def content(self):
            return wsgi_app_template % {
                'auto_reload': repr(self.auto_reload),
                'settings_module': repr(self.parent.settings_module),
            }

        def setup(self):
            self.host.sudo("mkdir -p $(dirname '%s')" % self.remote_path)
            Config.setup(self)
            self.host.sudo("chown %s '%s'" % (self.parent.username, self.remote_path))
