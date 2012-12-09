from deployer.service import Service, isolate_host
from deployer.contrib.services.apt_get import AptGet
from deployer.contrib.services.config import Config

import ConfigParser
import StringIO


@isolate_host
class PHP(Service):
    """
    PHP installation with FPM and APC.
    (http://www.opendev.be/compilation-de-nginx-php53-fpm-et-apc-sous-linux/)
    """
    #php_url = 'http://be2.php.net/distributions/php-5.3.8.tar.bz2'
    php_url = 'http://be2.php.net/distributions/php-5.4.3.tar.bz2'

    php_dir = '/opt/php-5'
    apc_url = 'http://pecl.php.net/get/APC-3.1.9.tgz'

    username = 'www-data'
    groupname = 'www-data'

    fcgi_listen = '127.0.0.1:9000'

    class packages(AptGet):
        packages = (
                'libpcre3-dev',
                'zlib1g-dev',
                'libssl-dev',
                'libxml2-dev',
                'libmcrypt-dev',
                'libltdl-dev',
                'libpng12-dev',
                'libjpeg8-dev',
                'bzip2',
                'autoconf',
                'make')


    def _init(self, cmd):
        for h in self.hosts:
            h.sudo('/etc/init.d/php-fpm %s' % cmd)

    def start(self):
        self._init('start')

    def stop(self):
        self._init('stop')

    def status(self):
        self._init('status')


    def setup(self):
        self.packages.install()
        self._install_php()
        self._install_apc()
        self._configure_php()
        self.fpm_config.setup()

    def _install_php(self):
        """
        Compile and install PHP
        """
        for h in self.hosts:
            h.run("wget '%s'" % self.php_url)
            h.run("tar -jxvf php-5.*.*.bz2")
            with h.cd('php-5.*.*/'):
                # Compile PHP
                h.run('./configure --prefix=%s --enable-fpm --with-mysql=mysqlnd '
                                '--with-mysqli=mysqlnd --with-pdo-mysql=mysqlnd --with-mcrypt '
                                '--enable-mbstring --with-gd --with-zlib' % self.php_dir)
                h.run('make')
                h.sudo('make install')

                # Copy default configuration files
                h.sudo('cp php.ini-production %s/lib/php.ini' % self.php_dir)
                h.sudo('cp php.ini-production %s/lib/php.ini.example' % self.php_dir)

                h.sudo('cp sapi/fpm/php-fpm.conf %s/etc/php-fpm.conf' % self.php_dir)
                h.sudo('cp sapi/fpm/php-fpm.conf %s/etc/php-fpm.conf.example' % self.php_dir)

                # Install Init.d files
                h.sudo('cp sapi/fpm/init.d.php-fpm /etc/init.d/php-fpm')
                h.sudo('chmod u+x /etc/init.d/php-fpm')


    def _install_apc(self):
        """
        Install the APC extension.
        """
        for h in self.hosts:
            h.run("wget '%s'" % self.apc_url)
            h.run('tar -zxvf APC-3*.tgz')

            with h.cd('APC-3*/'):
                h.run('%s/bin/phpize' % self.php_dir)
                h.run('./configure --with-php-config=%s/bin/php-config' % self.php_dir)
                h.run('make')

                h.sudo('make install')


    def _configure_php(self):
        """
        Add APC extension to php.ini
        """
        for h in self.hosts:
            # Read original config
            config = ConfigParser.RawConfigParser()#allow_no_value=True)
            config.readfp(h.open('%s/lib/php.ini' % self.php_dir, 'r'))

            # Change settings
            config.set('Date', 'date.timezone', 'Europe/Brussels')
            config.set('PHP', 'extension', '%s/lib/php/extensions/no-debug-non-zts-20090626/apc.so' % self.php_dir)

            # Write config back
            config.write(h.open('%s/lib/php.ini' % self.php_dir, 'w', use_sudo=True))


    class fpm_config(Config):
        """
        php-fpm configuration.
        """
        use_sudo = True

        @property
        def remote_path(self):
            return '%s/etc/php-fpm.conf' % self.parent.php_dir

        @property
        def content(self):
            config = ConfigParser.RawConfigParser()

            # Change settings
            config.add_section('global')
            config.set('global', 'pid', 'run/php-fpm.pid')

            config.add_section('www')
            config.set('www', 'user', self.parent.username)
            config.set('www', 'group', self.parent.groupname)
            config.set('www', 'listen', self.parent.fcgi_listen)
            config.set('www', 'pm', 'dynamic')
            config.set('www', 'pm.max_children', 40)
            config.set('www', 'pm.start_servers', 20)
            config.set('www', 'pm.min_spare_servers', 5)
            config.set('www', 'pm.max_spare_servers', 35)
            config.set('www', 'listen.allowed_clients', '127.0.0.1')

            output = StringIO.StringIO()
            config.write(output)
            return output.getvalue()
