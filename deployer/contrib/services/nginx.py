from deployer.service import Service, map_roles, required_property, isolate_host
from deployer.utils import esc1
from deployer.contrib.services.apt_get import AptGet
from deployer.contrib.services.config import Config
from deployer.contrib.services.hba import AllowEveryone
from deployer.contrib.services.variants import Variants
from deployer.query import Q
from deployer.host import Host

from pygments.lexers import NginxConfLexer
from operator import attrgetter


nginx_domain_redirect_stub = \
"""
# Domain redirect
server {
    listen %(port)s;
    server_name %(redirect_from_server_names)s;
    rewrite ^ %(protocol)s://%(server_name)s$request_uri? permanent;
}
"""

nginx_ssl_redirect_stub = \
"""
# SSL Redirect
server {
    listen %(port)s;
    server_name %(server_name)s;
    rewrite ^ https://%(server_name)s$request_uri? permanent;
}
"""


nginx_http_auth_stub = \
"""
    # Authentication
    auth_basic "Restricted";
    auth_basic_user_file %(htpasswd_file)s;
"""

nginx_ssl_stub = \
"""
    # SSL
    ssl_certificate %(ssl_certificate)s;
    ssl_certificate_key %(ssl_certificate_key)s;
"""

nginx_server_config_template = \
"""
%(domain_redirect_stub)s
%(ssl_redirect_stub)s


server {
    %(config_prefix)s

    # Compression
    #gzip              on;
    gzip_disable      "MSIE [1-6]\.(?!.*SV1)";
    gzip_static       on;
    gzip_buffers      16 8k;
    gzip_comp_level   9;
    gzip_http_version 1.0;
    gzip_min_length   0;
    gzip_types        text/plain text/html text/css application/json application/x-javascript text/xml application/xml application/xml+rss text/javascript image/x-icon image/bmp;
    gzip_vary         on;

    # Upload size
    client_max_body_size    10M;
    client_body_buffer_size 128k;

    # Authentication
    satisfy %(satisfy)s;

    %(authentication_stub)s

    %(restrict_access_to)s

    # Logs
    access_log %(access_log)s combined;
    error_log %(error_log)s;

    %(proxy_stub)s

    %(ssl_stub)s

    listen %(port)s %(ssl)s;
    server_name %(server_names)s;

    %(server_extra_config)s
}
"""

@isolate_host
class Nginx(Service):
    # Slug. Should be unique between all Nginx instances on one host.
    slug = required_property()

    class packages(AptGet):
        # Required packages for nginx
        packages = ( 'nginx',)

    class variants(Variants):
        slug = 'nginx'

        @property
        def variants(self):
            # TODO: add other variants, depending on the needs of subservices.
            for name, subservice in self.parent.get_subservices():
                if subservice.isinstance(Server):
                    if subservice.enable_ssl:
                        yield 'ssl'


    def setup(self):
        """
        Install, configure and start nginx
        """
        # Install nginx
        self.packages.install()

        self.config.setup()

        for name, subservice in self.get_subservices():
            if subservice.isinstance(Server) and not name.startswith('_'):
                subservice.setup()

        # (Re)start nginx
        self.hosts.filter('host').sudo('service nginx restart')

    # Start/stop nginx process

    def start(self):
        self.hosts.filter('host').sudo('service nginx start') # TODO: use sysvinitservice class here

    def stop(self):
        self.hosts.filter('host').sudo('service nginx stop')

    def restart(self):
        self.hosts.filter('host').sudo('service nginx restart')

    def reload(self):
        self.hosts.filter('host').sudo('service nginx reload')

    def status(self):
        self.hosts.filter('host').sudo('service nginx status')

    # Nginx configuration

    @map_roles.just_one
    class config(Config):
        @property
        def remote_path(self):
            return '/etc/nginx/sites-available/%s' % self.parent.slug

        use_sudo = True
        lexer = NginxConfLexer

        def test(self):
            print 'Testing remote config'
            self.hosts.sudo("nginx -t -c '/etc/nginx/nginx.conf'")

        @property
        def content(self):
            parts = []

            # Find all configuration parts.
            for name, subservice in self.parent.get_subservices():
                if subservice.isinstance((Server, Upstream)) and not name.startswith('_'):
                    parts.append(subservice)

            # Order parts
            parts = sorted(parts, key=attrgetter('_service_creation_counter'))

            return ''.join(p.config for p in parts)

        def setup(self):
            # Install config
            Config.setup(self)

            # Symlink from sites-enabled/slug (If this one does not yet exist)
            slug = self.parent.slug

            for h in self.hosts:
                if not h.exists('/etc/nginx/sites-enabled/%s' % slug):
                    h.sudo("ln -s '/etc/nginx/sites-available/%s' '/etc/nginx/sites-enabled/%s'" % (esc1(slug), esc1(slug)))


class Server(Service):
    """
    "server { ...}" section in Nginx config.
    """
    slug = Q.parent.slug # Normally, a server is nested in a Nginx class,
                         # and if we have only one server instance here, it is
                         # logical to take the same slug.

    # Host name(s) (for virtual hosting)
    server_names = [ 'localhost' ]

    # Redirect these virtual hosts, to `server_name`
    redirect_from_server_names = () # List of strings

    # Listen to this port
    port = 80
    ssl_port = 443

    upstream_log_format_name = property(lambda s: 'upst-%s' % s.slug)
    upstream_log_format = property(lambda s: "log_format %s '$remote_addr - $remote_user [$time_local]  $request - $upstream_addr - upstream_response_time $upstream_response_time';" % s.upstream_log_format_name)

    # =======[ Authentication / Access ]======

    # Satisfy 'all' or 'any'. Access policy
    satisfy = 'all'

    # HTTP authentication
    enable_http_authentication = False
    http_credentials = { } # e.g. { 'username': 'password' }

    # Proxy
    proxy_settings = {
            'proxy_redirect': 'off',
            'proxy_set_header X-Real-IP': '$remote_addr',
            'proxy_set_header X-Forwarded-For': '$proxy_add_x_forwarded_for',
            'proxy_set_header Host': '$host',
            }

    proxy_extra_settings = {}

    # =======[ SSL ]======

    # SSL
    enable_ssl = False
    force_https = False
    ssl_certificate = ''
    ssl_certificate_key = ''

    def setup(self):
        if self.enable_http_authentication:
            self.htpasswd.setup()

        if self.enable_ssl:
            self.install_certificates()

    # Access restriction
    host_based_access = AllowEveryone

    access_log = Q('/var/log/nginx/%s.access.log') % Q.slug

    error_log = Q('/var/log/nginx/%s.error.log') % Q.slug

    # HTTP Authentication

    @map_roles.just_one # TODO: why 'just_one'?
    class htpasswd(Config):
        use_sudo = True
        remote_path = Q('/etc/nginx/htpasswd-%s') % Q.parent.slug

        @property
        def content(self):
            # Generate htpasswd content based on credentials
            import crypt
            output = []
            seed = 'M9' # TODO: I think the seed should be random...

            for username, password in self.parent.http_credentials.items():
                output.append('%s:%s' % (username, crypt.crypt(password, seed)))

            output.append('')
            return '\n'.join(output)

    # SSL
    ssl_certificate_file = Q('/etc/nginx/certificate-%s.crt') % Q.slug
    ssl_certificate_key_file = Q('/etc/nginx/certificate-%s.key') % Q.slug

    def install_certificates(self):
        """
        Install SSL certificates.
        """
        if self.enable_ssl:
            print 'Installing certificates...'
        else:
            print 'WARNING: Installing certificates but "enable_ssl" is False  ...'

        for h in self.hosts.filter('host'):
            h.open(self.ssl_certificate_file, 'wb', use_sudo=True).write(self.ssl_certificate)
            h.open(self.ssl_certificate_key_file, 'wb', use_sudo=True).write(self.ssl_certificate_key)


    @property
    def config(self):
        # Domain redirects
        if self.redirect_from_server_names:
            domain_redirect_stub = nginx_domain_redirect_stub % {
                    'redirect_from_server_names': ' '.join(self.redirect_from_server_names),
                    'server_name': self.server_names[0],
                    'port': self.port,
                    'protocol': ('https' if self.enable_ssl else 'http'),
                }
        else:
            domain_redirect_stub = ''

        if self.enable_ssl:
            ssl_redirect_stub = nginx_ssl_redirect_stub  % {
                    'port': self.port,
                    'server_name': self.server_names[0],
                }
        else:
            ssl_redirect_stub = ''

        # Authentication stub
        if self.enable_http_authentication:
            authentication_stub = nginx_http_auth_stub % { 'htpasswd_file': self.htpasswd.remote_path }
        else:
            authentication_stub = ''

        # Restrict access
        if not self.host_based_access.allow_everyone:
            restrict = '\n'.join('\tallow %-38s; # %s' % t for t in self.host_based_access.allow_tuples) + '\n\tdeny all;\n'
        else:
            restrict = '\n'

        # SSL
        if self.enable_ssl:
            ssl_stub = nginx_ssl_stub % {
                    'ssl_certificate': self.ssl_certificate_file,
                    'ssl_certificate_key': self.ssl_certificate_key_file, }
        else:
            ssl_stub = ''

        return nginx_server_config_template % {
                'domain_redirect_stub': domain_redirect_stub,
                'ssl_redirect_stub': ssl_redirect_stub,
                'access_log': self.access_log,
                'authentication_stub': authentication_stub,
                'error_log': self.error_log,
                'server_names': ' '.join(self.server_names),
                'satisfy': self.satisfy,
                'restrict_access_to': restrict,
                'proxy_stub': self.proxy_stub,
                'ssl_stub': ssl_stub,
                'slug': self.slug,
                'port': (self.ssl_port if self.enable_ssl else self.port),
                'ssl': ('ssl' if self.enable_ssl else ''),
                'config_prefix': self.server_config_prefix,
                'server_extra_config': self.server_extra_config,
            }

    @property
    def proxy_stub(self):
        proxy_extra_settings = dict(self.proxy_extra_settings)
        if self.enable_ssl:
            proxy_extra_settings.update({
                'proxy_set_header X_FORWARDED_PROTOCOL': 'https',
                'proxy_set_header X_FORWARDED_SSL': 'on',
                })

        proxy_config = '# Proxy settings\n'
        proxy_default_settings = {}
        for k, v in self.proxy_settings.items():
            if not proxy_extra_settings.has_key(k):
                proxy_default_settings[k] = v

        if 0 < len(proxy_default_settings):
            proxy_config += '    # Default\n'
            proxy_config += '\n'.join(["    %-50s %s;" % (k, v) for k, v in proxy_default_settings.items()])

        if 0 < len(proxy_extra_settings):
            proxy_config += '\n    # Extra\n'
            proxy_config += '\n'.join(["    %-50s %s;" % (k, v) for k, v in proxy_extra_settings.items()])

        return proxy_config

    @property
    def server_config_prefix(self):
        return self.upstream_log_format

    @property
    def server_extra_config(self):
        """
        The config of all Part subservices, joined.
        """
        parts = []

        # Find all configuration parts.
        for name, subservice in self.get_subservices():
            if subservice.isinstance(Part) and not name.startswith('_'):
                parts.append(subservice)

        # Order parts
        parts = sorted(parts, key=attrgetter('_service_creation_counter'))

        def get_config(part):
            return part.config if part.enabled else ''
                # TODO: it may be possible to wrap it in if(0){..} as well.

        return ''.join(get_config(p) for p in parts)

    # Monitoring

    def tail_error_log(self):
        self.hosts.filter('host').sudo("tail -f '%s'" % esc1(self.error_log), ignore_exit_status=True)


    def tail_access_log(self):
        self.hosts.filter('host').sudo("tail -f '%s'" % esc1(self.access_log), ignore_exit_status=True)


# Parts to plug into the Site

class Part(Service):
    config = required_property()
    enabled = True


class UwsgiPass(Part):
    uwsgi_socket = required_property()
    maintenance_file = '/etc/enable-maintenance'
    location = '/'
    location_prefix = '' # e.g. '~' or '~*'
    bypass_auth_basic = False

    _config = """
    # Uwsgi pass
    location %(location_prefix)s %(location)s {
        if (-f %(maintenance_file)s){
            return 503;
        }
        access_log %(upstream_access_log)s %(upstream_log_format_name)s;
        uwsgi_pass %(uwsgi_socket)s;
        include uwsgi_params;
        %(basic_auth)s
        %(extra)s
    }
    """

    @property
    def config(self):
        # Prefix socket with 'unix:' when it starts with a slash.
        # In that case, we are using in socket instead of an IP/port.
        socket = self.uwsgi_socket
        if socket.startswith('/'):
            socket = 'unix:%s' % socket

        return self._config % {
                    'upstream_access_log': self.upstream_access_log,
                    'upstream_log_format_name': self.parent.upstream_log_format_name,
                    'uwsgi_socket': socket,
                    'slug': self.parent.slug,
                    'maintenance_file': self.maintenance_file,
                    'location': self.location,
                    'location_prefix': self.location_prefix,
                    'basic_auth': ('auth_basic off;' if self.bypass_auth_basic else ''),
                    'extra': self.extra,
            }

    @property
    def extra(self):
        # Override
        return ''

    @property
    def upstream_access_log(self):
        return '/var/log/nginx/%s.upstream-access.log' % self.parent.slug

    def tail_upstream_access_log(self):
        self.hosts.filter('host').sudo("tail -f '%s'" % esc1(self.upstream_access_log), ignore_exit_status=True)


    # Maintanance mode. Turns site into 503 Service Temporarily Unavailable

    def start_maintenance(self):
        for h in self.hosts.filter('host'):
            h.sudo("touch '%s'" % esc1(self.maintenance_file))

    def stop_maintenance(self):
        for h in self.hosts.filter('host'):
            h.sudo("rm '%s'" % esc1(self.maintenance_file))


class ProxyPass(Part):
    proxy_pass_url = required_property()
    proxy_pass_slug = Q.parent.slug
    location = '/'
    location_prefix = '' # e.g. '~' or '~*'

    # Config stub
    _config = """
    # Proxy
    location %(location_prefix)s %(location)s {
        proxy_pass %(proxy_pass_url)s;
        access_log %(upstream_access_log)s %(upstream_log_format_name)s;
    }
    """

    @property
    def config(self):
        return self._config % { 'proxy_pass_url': self.proxy_pass_url,
                    'location': self.location,
                    'location_prefix': self.location_prefix,
                    'slug': self.parent.slug,
                    'upstream_access_log': self.upstream_access_log,
                    'upstream_log_format_name': self.parent.upstream_log_format_name,
                    }


    @property
    def upstream_access_log(self):
        return '/var/log/nginx/%s.upstream-access.log' % self.proxy_pass_slug

    def tail_upstream_access_log(self):
        self.hosts.filter('host').sudo("tail -f '%s'" % esc1(self.upstream_access_log), ignore_exit_status=True)


class Media(Part):
    _config = """
    # Media
    location %(location_prefix)s %(location)s {
        alias %(alias)s;
        expires %(expires)s;
        %(extra)s
        break;
    }
    """
    location = required_property()
    location_prefix = '~'
    alias = required_property()
    bypass_auth_basic = False
    expires = 'max'

    @property
    def config(self):
        return self._config % {
                'location': self.location,
                'location_prefix': self.location_prefix,
                'alias': self.alias,
                'expires': self.expires,
                'extra': ('auth_basic off;' if self.bypass_auth_basic else ''),
        }


class Upstream(Part):
    class Meta(Part.Meta):
        roles = ('backends', )

    slug = required_property()
    port = 80

    # Change this method if you want to use the external address, for example
    get_address = lambda s, h: h.get_ip_address()

    @property
    def config(self):
        o = [ 'upstream %s {\n' % self.slug ]
        for h in self.hosts:
            o.append('    server %s:%s; # %s\n' % (self.get_address(h), self.port, h.slug))
        o += [ '}\n' ]
        return ''.join(o)


class PHP(Part):
    # Config stub
    _config = """
    location / {
        root %(root)s;
        index index.php index.html index.htm;
    }
    location ~ \.php$ {
        root %(root)s;
        try_files $uri =404;
        fastcgi_split_path_info ^(.+\.php)(/.+)$;
        include fastcgi_params;
        fastcgi_index index.php;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
        fastcgi_pass 127.0.0.1:9000;
    }
    """
    document_root = required_property()

    @property
    def config(self):
        return self._config % { 'root': self.document_root }


# Specific site configurations

class ProxyPassSite(Nginx):
    """
    Use nginx as a proxy to another HTTP site.
    """
    proxy_pass_url = 'http://localhost:9000'

    class server(Server):
        class proxy_pass(ProxyPass):
            proxy_pass_url = Q.parent.proxy_pass_url



class UwsgiSite(Nginx):
    uwsgi_socket = '127.0.0.1:3032'
    maintenance_file = '/etc/enable-maintenance'

    class server(Server):
        class uwsgi(UwsgiPass):
            uwsgi_socket = Q.parent.uwsgi_socket
            maintenance_file = Q.parent.maintenance_file



class StaticSite(Nginx):
    """
    Use nginx only for serving static files.
    """
    @property
    def www_dir(self):
        """
        Path to the document root of this static site.
        """
        raise NotImplementedError('No www_dir given')

    class server(Server):
        slug = 'static'

        class media(Media):
            location = '^/(.*)$'
            alias = Q('%s/$1') % Q.parent.www_dir


class PHPSite(Nginx):
    """
    Nginx / FPM / PHP

    See:
    http://www.opendev.be/compilation-de-nginx-php53-fpm-et-apc-sous-linux/
    """
    document_root = required_property()
    server_names = required_property()

    class server(Server):
        slug = 'php'
        server_names = Q.parent.server_names

        class php(PHP):
            document_root = Q.parent('PHPSite').document_root
