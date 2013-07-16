from deployer.contrib.nodes.config import Config
from deployer.query import Q
from deployer.node import SimpleNode, required_property
from deployer.utils import esc1, indent

from pygments.lexers import BashLexer


upstart_template = \
"""
description '%(description)s'
author      '%(author)s'

start on %(start_on)s
stop on %(stop_on)s

chdir '%(chdir)s'
exec %(command)s
respawn
%(extra)s

%(extra_scripts)s
"""

class UpstartService(SimpleNode):
    chdir = '/'
    user = 'root'
    author = '(author)'
    command = required_property() # e.g. '/bin/sleep 1000'
    pre_start_script = ''
    start_on = 'runlevel [2345]'
    stop_on = 'runlevel [016]'
    post_start_script = ''
    pre_stop_script = ''
    post_stop_script = ''
    extra = ''

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

    class config(Config):
        remote_path = Q.parent.config_file
        use_sudo = True
        lexer = BashLexer # No UpstartLexer available yet?

        @property
        def content(self):
            self = self.parent

            extra_scripts = ''
            for s in ('start', 'stop'):
                for p in ('pre', 'post'):
                    script = getattr(self, '%s_%s_script' % (p, s), '')
                    if script:
                        extra_scripts += """
%s-%s script
%s
end script
""" % (p, s, indent(script))

            return upstart_template % {
                    'description': esc1(self.description),
                    'author': esc1(self.author),
                    'chdir': esc1(self.chdir),
                    'start_on': self.start_on,
                    'stop_on': self.stop_on,
                    'command': self.full_command,
                    'user': esc1(self.user),
                    'extra': self.extra,
                    'extra_scripts': extra_scripts,
                }

    def setup(self):
        """
        Install upstart configuration
        """
        self.config.setup()

    def start(self):
        self.host.sudo('start "%s" || true' % self.slug)

    def stop(self):
        self.host.sudo('stop "%s" || true' % self.slug)

    def restart(self):
        self.host.sudo('restart "%s" || true' % self.slug)

    def status(self):
        self.host.sudo('status "%s"' % self.slug)

    def run_in_shell(self):
        with self.host.cd(self.chdir):
            self.host.sudo(self.full_command)

    def is_already_installed(self):
        """
        True when this service is installed.
        """
        return self.host.exists(self.config_file)
