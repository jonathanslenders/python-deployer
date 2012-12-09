from deployer.contrib.services import nginx
from deployer.contrib.services.apt_get import AptGet
from deployer.contrib.services.config import Config
from deployer.contrib.services.php import PHP
from deployer.query import Q
from deployer.service import Service, required_property, isolate_host
from deployer.utils import esc1

from pygments.lexers import PhpLexer

import urllib


wp_config = \
"""
<?php
/* Database settings */
define('DB_NAME', '%(database_name)s');
define('DB_USER', '%(database_user)s');
define('DB_PASSWORD', '%(database_password)s');
define('DB_HOST', '%(database_host)s');
define('DB_CHARSET', 'utf8');
define('DB_COLLATE', '');

$table_prefix  = '%(table_prefix)s';

define('WPLANG', '');

define('WP_DEBUG', false);

/* Unique keys */
%(keys)s

/* Don't edit below */
if ( !defined('ABSPATH') )
  define('ABSPATH', dirname(__FILE__) . '/');

require_once(ABSPATH . 'wp-settings.php');
?>
"""


@isolate_host
class Wordpress(Service):
    url = "http://wordpress.org/latest.zip"
    slug = 'wordpress'
    server_names = ['localhost']

    database_name = required_property()
    database_user = required_property()
    database_password = required_property()
    database_host = required_property()
    table_prefix = 'wp_'


    class packages(AptGet):
        packages = ('unzip',)


    @property
    def document_root(self):
        raise NotImplementedError('No document root given for wordpress')

    def setup(self):
        self.packages.install()
        self.download_wordpress()
        self.php.setup()
        self.config.setup()
        self.nginx.setup()

    def download_wordpress(self):
        for h in self.hosts:
            if not h.exists(self.document_root):
                h.run("wget '%s' --output-document wordpress.zip" % self.url)
                h.run("unzip wordpress.zip")
                h.run("mv wordpress '%s'" % esc1(self.document_root))


    class php(PHP):
        pass


    class nginx(nginx.PHPSite):
        document_root = Q.parent.document_root
        slug = Q.parent.slug
        server_names = Q.parent.server_names


    class config(Config):
        @property
        def remote_path(self):
            return self.parent.document_root + '/wp-config.php'

        lexer = PhpLexer

        @property
        def content(self):
            self = self.parent

            return wp_config % {
                'database_name': self.database_name,
                'database_user': self.database_user,
                'database_password': self.database_password,
                'database_host': self.database_host,
                'table_prefix': self.table_prefix,

                # Keys are generated on the fly, during release
                'keys': urllib.urlopen('https://api.wordpress.org/secret-key/1.1/salt/').read(),
            }
