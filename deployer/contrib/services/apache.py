from deployer.service import Service, isolate_host
from deployer.contrib.services.apt_get import AptGet
from deployer.contrib.services.sysvinit import SysVInitService
from deployer.utils import esc1


@isolate_host
class Apache(Service):
    sites = {'default': False}
    modules = ('expires',)
    ports = (80,)

    class packages(AptGet):
        packages = ('apache2', 'libapache2-mod-rpaf', 'libapache2-mod-wsgi')

    class init_service(SysVInitService):
        slug = 'apache2'
        no_pty = True

    def setup(self):
        self.packages.install()

        self.setup_config()

        for port in self.ports:
            self.add_port(port)

        for module in self.modules:
            self.enable_module(module)

        for site, info in self.sites.items():
            if not info:
                self.disable_site(site)
            else:
                site_file = enable = False
                if isinstance(info, basestring):
                    site_file = info
                else:
                    site_file = info[0]
                    enable = info[1]
                self.install_site(site, site_file)
                if enable:
                    self.enable_site(site)

        self.init_service.restart()

    def setup_config(self):
        for host in self.hosts:
            if not host.exists("/etc/apache2/ports.conf.disabled"):
                self.hosts.sudo("mv /etc/apache2/ports.conf /etc/apache2/ports.conf.disabled")
                self.hosts.sudo("echo '# Empty, see conf.d/port-N' > /etc/apache2/ports.conf")

    def enable_module(self, module):
        self.hosts.sudo('a2enmod %s' % module)

    def disable_module(self, module):
        self.hosts.sudo('a2dismod %s' % module)

    def enable_site(self, site):
        self.hosts.sudo('a2ensite %s' % site)

    def disable_site(self, site):
        self.hosts.sudo('a2dissite %s' % site)

    def install_site(self, site, file):
        self.hosts.sudo("ln -fs '%s' /etc/apache2/sites-available/%s" % (esc1(file), site))

    def add_port(self, port):
        port_config = [
                'NameVirtualHost *:%s' % port,
                'Listen %s' % port,
                ]
        for host in self.hosts:
            host.open("/etc/apache2/conf.d/port-%s" % port, "w", use_sudo=True).write('\n'.join(port_config))

    def remove_port(self, port):
        self.hosts.sudo("rm -f /etc/apache2/conf.d/port-%s" % port)
