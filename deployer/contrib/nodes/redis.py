from deployer.contrib.commands import wget
from deployer.contrib.nodes.apt_get import AptGet
from deployer.contrib.nodes.config import Config
from deployer.contrib.nodes.upstart import UpstartService
from deployer.query import Q
from deployer.node import SimpleNode, required_property
from pygments.lexers import IniLexer
from deployer.utils import esc1


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

# Close the connection after a client is idle for N seconds (0 to disable)
timeout %(timeout)s

# Logfile
logfile %(logfile)s

%(bind)s
"""

class Redis(SimpleNode):
    """
    Key/Value storage server
    """
    # Port and slug should be unique between all redis installations on one
    # host.
    port = 6379
    database = 0
    password = None
    slug = required_property()

    timeout = 0

    # username for the server process
    username = required_property()

    # Bind to interface, e.g. '127.0.0.1'
    bind = None

    # Download URL
    redis_download_url = 'http://redis.googlecode.com/files/redis-2.6.13.tar.gz'

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

    @property
    def logfile(self):
        return '/var/log/redis-%s.log' % self.slug

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
        slug = Q('redis-%s') % Q.parent.slug
        chdir = '/'
        user = Q.parent.username
        command = Q('/usr/local/bin/redis-server %s') % Q.parent.config_file


    def setup(self):
        # Also make sure that redis was not yet installed
        if self.is_already_installed:
            print 'Warning: Redis is already installed'
            if not self.console.confirm('Redis is already installed. Reinstall?', default=False):
                return

        # Install dependencies
        self.packages.install()

        # Download, compile and install redis
        # If not yet installed
        if not self.host.has_command('redis-server'):
            # Download redis
            self.host.run(wget(self.redis_download_url, 'redis.tgz'))
            self.host.run('tar xvzf redis.tgz')

            # Unset ARCH variable, otherwise redis doesn't compile.
            # http://comments.gmane.org/gmane.linux.slackware.slackbuilds.user/6686
            with self.host.env('ARCH', ''):
                # Make and install
                with self.host.cd('redis-2.*'):
                    if self.host.is_64_bit:
                        self.host.run('make ARCH="-m64"')
                    else:
                        self.host.run('make 32bit')
                    self.host.sudo('make install')

        self.config.setup()
        self.upstart_service.setup()
        self.upstart_service.start()
        self.touch_logfile()

    def tail_logfile(self):
        self.host.sudo("tail -n 20 -f '%s'" % esc1(self.logfile))

    @property
    def is_already_installed(self):
        """
        Returns true when redis was already installed on all hosts
        """
        return self.host.exists(self.config_file) and self.upstart_service.is_already_installed()


    def shell(self):
        print 'Opening telnet connection to Redis... Press Ctrl-C to exit.'
        print
        self.host.run('redis-cli -h localhost -a "%s" -p %s' % (self.password or '', self.port))


    def monitor(self):
        """
        Monitor all commands that are currently executed on this redis database.
        """
        self.host.run('echo "MONITOR" | redis-cli -h localhost -a "%s" -p %s' % (self.password or '', self.port))


    def dbsize(self):
        """
        Return the number of keys in the selected database.
        """
        self.host.run('echo "DBSIZE" | redis-cli -h localhost -a "%s" -p %s' % (self.password or '', self.port))


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
                    'timeout': str(int(self.timeout)),
                    'logfile': self.logfile,
                }

        def setup(self):
            Config.setup(self)
            self.host.sudo("chown '%s' '%s' " % (self.parent.username, self.remote_path))

    def touch_logfile(self):
        # Touch and chown logfile.
        self.host.sudo("touch '%s'" % esc1(self.logfile))
        self.host.sudo("chown '%s' '%s'" % (esc1(self.username), esc1(self.logfile)))

    def info(self):
        """
        Get information and statistics about the server
        """
        self.host.run('echo "INFO" | redis-cli -h localhost -a "%s" -p %s' % (self.password or '', self.port))
