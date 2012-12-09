from deployer.service import Service
from deployer.contrib.services.apt_get import AptGet
from deployer.contrib.services.sysvinit import SysVInitService
from deployer.contrib.services.config import Config

memcached_server_config_template = \
"""
# Run as daemon (implied anyway)
-d

# Log output
logfile %(logfile)s

# Memory limit in MiB (default 64 MiB)
-m %(memory)s

# Port (default 11211)
-p %(port)s

# User (make sure this user exists)
-u %(user)s
"""

class MemcachedServer(Service):
    version = '1.4.9'

    # Configuration settings

    memory = 256
    logfile = '/var/log/memcached.log'
    port = 11211
    user = 'root'

    class build_requirements(AptGet):
        packages = ('libevent-dev', 'build-essential')

    class init_service(SysVInitService):
        slug = 'memcached'
#        no_pty = True

    def setup(self):
        self.build_from_source(self.version)

        self.config.setup()
        self.init_service.install()
        self.init_service.start()

    def build_from_source(self, version, reinstall=False):
        self.build_requirements.install()
        for host in self.hosts:
            if host.exists('/usr/bin/memcached') and not reinstall:
                continue
            host.run('mkdir -p src')
            with host.cd('src'):
                host.run("wget http://memcached.googlecode.com/files/memcached-%s.tar.gz" % self.version)
                host.run("tar xf memcached-%s.tar.gz" % self.version)
                with host.cd("memcached-%s" % self.version):
                    # Install in /usr, not /usr/local
                    # This allows us to use the provided memcached-init script without changes
                    # (which also expects the scripts folder in /usr/share/memcached/scripts)
                    build_args = ['--prefix=',
                            '--exec-prefix=/usr',
                            '--datarootdir=/usr',
                            '--enable-64bit']
                    host.run('./configure %s' % ' '.join(build_args))
                    host.run('make')
                    host.sudo('make install')
                    host.sudo('mkdir -p /usr/share/memcached')
                    host.sudo('cp -R scripts /usr/share/memcached')
            host.sudo('cp /usr/share/memcached/scripts/memcached-init /etc/init.d/memcached')

    class config(Config):
        remote_path = '/etc/memcached.conf'

        @property
        def content(self):
            return memcached_server_config_template % {
                    'logfile': self.parent.logfile,
                    'memory': self.parent.memory,
                    'port': self.parent.port,
                    'user': self.parent.user,
                    }

class MemcachedClient(Service):
    version = '0.53'

    class build_requirements(AptGet):
        packages = ('libevent-dev', 'build-essential', 'libcloog-ppl0', 'libcloog-ppl-dev')

    def setup(self):
        self.build_from_source(self.version)

    def build_from_source(self, version, reinstall=False):
        self.build_requirements.install()
        for host in self.hosts:
            if host.exists('/usr/local/lib/libmemcached.so') and not reinstall:
                continue
            host.run('mkdir -p src')
            with host.cd('src'):
                host.run("wget http://launchpad.net/libmemcached/1.0/%s/+download/libmemcached-%s.tar.gz" % (self.version, self.version))
                host.run("tar xf libmemcached-%s.tar.gz" % self.version)
                with host.cd("libmemcached-%s" % self.version):
                    host.run('./configure')
                    host.run('make')
                    host.sudo('make install')
            host.sudo('ldconfig')
