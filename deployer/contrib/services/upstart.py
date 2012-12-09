from deployer.contrib.services.config import Config
from deployer.query import Q
from deployer.service import Service, required_property, isolate_host, map_roles
from deployer.utils import esc1, indent

from pygments.lexers import BashLexer


upstart_template = \
"""
description '%(description)s'
author      '%(author)s'

start on startup
stop on shutdown

chdir '%(chdir)s'
exec %(command)s
respawn

%(post_stop_script)s
"""

post_stop_script_template = \
"""
post-stop script
%(content)s
end script
"""


@isolate_host
class UpstartService(Service):
    chdir = '/'
    user = 'root'
    author = '(author)'
    command = required_property() # e.g. '/bin/sleep 1000'
    post_stop_script = '' # No post stop script

    slug = required_property() # A /etc/init/(slug).conf file will be created

    @property
    def description(self):
        # Can be more verbose than the slug, e.g. 'Upstart Service'
        return self.slug

    @property
    def config_file(self):
        return '/etc/init/%s.conf' % self.slug

    @property
    def full_command(self):
        if self.user and self.user != 'root':
            return "su -c '%s' '%s' " % (esc1(self.command), esc1(self.user))
        else:
            return self.command

    @map_roles.just_one # The parent, UpstartService already has host isolation.
    class config(Config):
        remote_path = Q.parent.config_file
        use_sudo = True
        lexer = BashLexer # No UpstartLexer available yet?

        @property
        def content(self):
            self = self.parent

            if self.post_stop_script:
                post_stop_script = post_stop_script_template % {
                        'content': indent(self.post_stop_script),
                    }

            else:
                post_stop_script = ''

            return upstart_template % {
                    'description': esc1(self.description),
                    'author': esc1(self.author),
                    'chdir': esc1(self.chdir),
                    'command': self.full_command,
                    'user': esc1(self.user),
                    'post_stop_script': post_stop_script,
                }

    def setup(self):
        """
        Install upstart configuration
        """
        self.config.setup()

    def start(self):
        self.hosts.sudo('start "%s" || true' % self.slug)

    def stop(self):
        self.hosts.sudo('stop "%s" || true' % self.slug)

    def restart(self):
        self.hosts.sudo('restart "%s" || true' % self.slug)

    def status(self):
        self.hosts.sudo('status "%s"' % self.slug)

    def run_in_shell(self):
        with self.hosts.cd(self.chdir):
            self.hosts.sudo(self.full_command)

    def is_already_installed(self):
        """
        True when this service is installed.
        """
        # Note: thanks to @isolate_host, there can only be one host in
        # self.hosts.filter('host')
        return self.hosts.filter('host')[0].exists(self.config_file)
