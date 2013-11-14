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
logfile %(log_file)s

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
    version = '2.6.16'
    tarball_name = Q('redis-%s.tar.gz') % Q.version
    srcdir_name = Q('redis-%s') % Q.version
    download_url = Q('http://download.redis.io/releases/%s') % Q.tarball_name

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

    config_dir = '/etc/redis'
    config_file = Q('%s/%s.log') % (Q.config_dir, Q.slug)

    log_dir = '/var/log/redis'
    log_file = Q('%s/%s.log') % (Q.log_dir, Q.slug)

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

        @property
        def pre_start_script(self):
            return """
mkdir -p %(log_dir)s; chmod 777 %(log_dir)s;
                """ % {
                        'log_dir': self.parent.log_dir,
                        }


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
            with self.host.cd('src'):
                if not self.host.exists(self.tarball_name):
                    self.host.run(wget(self.download_url))
                if not self.host.exists(self.srcdir_name):
                    self.host.run('tar xzf %s' % self.tarball_name)

                with self.host.cd(self.srcdir_name):
                    # Unset ARCH variable, otherwise redis doesn't compile.
                    # http://comments.gmane.org/gmane.linux.slackware.slackbuilds.user/6686
                    with self.host.env('ARCH', ''):
                        # Make and install
                        if self.host.is_64_bit:
                            self.host.run('make ARCH="-m64"')
                        else:
                            self.host.run('make 32bit')
                        self.host.sudo('make install')

        self.host.sudo('mkdir -p %s' % self.log_dir)
        self.host.sudo('chmod 777 %s' % self.log_dir)

        self.host.sudo('mkdir -p %s' % self.config_dir)

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
                    'timeout': str(int(self.timeout)),
                    'log_file': self.log_file,
                }

        def setup(self):
            Config.setup(self)
            self.host.sudo("chown '%s' '%s' " % (self.parent.username, self.remote_path))

    def touch_logfile(self):
        # Touch and chown logfile.
        # With log_file in log_dir, we chmod log_dir and this is not needed anymore
        self.host.sudo("touch '%s'" % esc1(self.log_file))
        self.host.sudo("chown '%s' '%s'" % (esc1(self.username), esc1(self.log_file)))

    def tail_log(self):
        self.host.sudo("tail -n 20 -f '%s'" % esc1(self.log_file))

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


    def info(self):
        """
        Get information and statistics about the server
        """
        self.host.run('echo "INFO" | redis-cli -h localhost -a "%s" -p %s' % (self.password or '', self.port))
