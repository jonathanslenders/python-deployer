from deployer.console import input
from deployer.contrib.commands import wget
from deployer.contrib.services.apt_get import AptGet
from deployer.contrib.services.config import Config
from deployer.contrib.services.upstart import UpstartService
from deployer.query import Q
from deployer.service import Service, required_property, isolate_host
from pygments.lexers import IniLexer


# /etc/redis.conf template
config_template = \
"""
# Redis configuration file

# Authentication
%(password)s

# Save location
dbfilename %(database_file)s
dir %(directory)s

# Auto save
# (after 60 seconds if at least one key has been changed)
# e.g. save 60 1
%(auto_save)s

port %(port)s

%(bind)s
"""

@isolate_host
class Redis(Service):
    """
    Key/Value storage server
    """
    # Port and slug should be unique between all redis installations on one
    # host.
    port = 6379
    slug = required_property()
    password = required_property()

    # username for the server process
    username = required_property()

    # Bind to interface, e.g. '127.0.0.1'
    bind = None

    # Download URL
        # redis_download_url = 'http://redis.googlecode.com/files/redis-2.4.18.tar.gz'
    redis_download_url = 'http://redis.googlecode.com/files/redis-2.6.7.tar.gz'

    # directory for the database file, or None for the home directory
    @property
    def directory(self):
      # Fallback to home directory
      return self.host.get_home_directory()

    # Make persisntent True, when you want to save this database to the disk.
    persistent = False

    @property
    def database_file(self):
        return 'redis-db-%s.rdb' % self.slug

    @property
    def config_file(self):
        return '/etc/redis-%s.conf' % self.slug

    class packages(AptGet):
        # Packages required for building redis
        packages = ('make', 'gcc',  'telnet', 'build-essential')
        # Depending on the system (x86 or 64bit), some packages are not available.
        packages_if_available = ('libc6-dev', 'libc6-dev-amd64', 'libc6-dev-i386',
                            'libjemalloc-dev')

    class upstart_service(UpstartService):
        """
        Redis upstart service.
        """
        @property
        def slug(self):
            return 'redis-%s' % self.parent.slug

        chdir = '/'

        @property
        def user(self):
            return self.parent.username

        @property
        def command(self):
            return '/usr/local/bin/redis-server %s' % self.parent.config_file


    def setup(self):
        # Also make sure that redis was not yet installed
        if self.is_already_installed:
            print 'Warning: Redis is already installed'
            if input('Redis is already installed. Reinstall?', answers=['y', 'n'], default='n') == 'n':
                return

        # Install dependencies
        self.packages.install()

        # Download, compile and install redis
        for h in self.hosts:
            # If not yet installed
            if not h.has_command('redis-server'):
                # Download redis
                h.run(wget(self.redis_download_url, 'redis.tgz'))
                h.run('tar xvzf redis.tgz')

                # Unset ARCH variable, otherwise redis doesn't compile.
                # http://comments.gmane.org/gmane.linux.slackware.slackbuilds.user/6686
                with h.env('ARCH', ''):
                    # Make and install
                    with h.cd('redis-2.*'):
                        if h.is_64_bit:
                            h.run('make ARCH="-m64"')
                        else:
                            h.run('make 32bit')
                        h.sudo('make install')

        self.config.setup()

        # Install upstart config, and run
        self.upstart_service.setup()
        self.upstart_service.start()

        print 'Redis setup successfully on host'


    class config(Config):
        remote_path = Q.parent.config_file
        lexer = IniLexer

        @property
        def content(self):
            self = self.parent
            return config_template % {
                    'database_file': self.database_file,
                    'directory': self.directory,
                    'password': ('requirepass %s' % self.password if self.password else ''),
                    'port': self.port,
                    'auto_save': 'save 60 1' if self.persistent else '',
                    'bind': ('bind %s' %  self.bind if self.bind else ''),
                }

        def setup(self):
            Config.setup(self)
            self.host.sudo("chown '%s' '%s' " % (self.parent.username, self.remote_path))


    @property
    def is_already_installed(self):
        """
        Returns true when redis was already installed on all hosts
        """
        return self.host.exists(self.config_file) and self.upstart_service.is_already_installed()


    def shell(self):
        print 'Opening telnet connection to Redis... Press Ctrl-C to exit.'
        print
        self.host.run('redis-cli -h localhost -a "%s" -p %s' % (self.password, self.port))


    def monitor(self):
        """
        Monitor all commands that are currently executed on this redis database.
        """
        self.host.run('echo "MONITOR" | redis-cli -h localhost -a "%s" -p %s' % (self.password, self.port))


    def dbsize(self):
        """
        Return the number of keys in the selected database.
        """
        self.host.run('echo "DBSIZE" | redis-cli -h localhost -a "%s" -p %s' % (self.password, self.port))


    def info(self):
        """
        Get information and statistics about the server
        """
        self.host.run('echo "INFO" | redis-cli -h localhost -a "%s" -p %s' % (self.password, self.port))
