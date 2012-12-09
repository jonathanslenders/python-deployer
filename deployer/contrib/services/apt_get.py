from deployer.contrib.commands import wget
from deployer.exceptions import ExecCommandFailed
from deployer.service import Service, isolate_host
from deployer.utils import esc1


DEFAULT_KEYSERVER = 'hkp://keyserver.ubuntu.com:80/'

@isolate_host
class AptGet(Service):
    packages = ()
    packages_if_available = ()
                # Packages to be installed when they're available.  Don't
                # throw errors when not available.
    dpkg_packages = ()
    extra_keys = ()
    extra_key_urls = ()
    extra_sources = {}

    def install(self, skip_update=True):
        """
        Install packages.
        """
        if not skip_update:
            self.update()

        # apt-get install
        with self.hosts.env('DEBIAN_FRONTEND', 'noninteractive'):
            self.hosts.sudo('apt-get install -yq %s' % ' '.join(self.packages))

            # Optional packages
            for p in self.packages_if_available:
                for h in self.hosts:
                    try:
                        h.sudo('apt-get install -yq %s' % p)
                    except ExecCommandFailed:
                        print 'Failed to install %s on %s, ignoring...' % (p, h.slug)

        # dpkg packages
        self.install_dpkg_packages()

    def update(self):
        self.hosts.sudo('apt-get update')

    def add_key_url(self, key_url):
        self.hosts.sudo("wget '%s' -O - | apt-key add -" % esc1(key_url))

    def add_key(self, fingerprint, keyserver=None):
        keyserver = keyserver if keyserver else DEFAULT_KEYSERVER
        self.hosts.sudo("apt-key adv --keyserver %s --recv %s" % (keyserver, fingerprint))

    def add_sources(self, slug, sources, overwrite=False):
        extra_sources_dir = '/etc/apt/sources.list.d'
        for host in self.hosts:
            if not host.exists('%s/%s.list' % (extra_sources_dir, slug)) or overwrite:
                host.open('%s/%s.list' % (extra_sources_dir, slug), 'w', use_sudo=True).write("\n".join(sources))

    def setup_extra(self):
        self.setup_extra_keys()
        self.setup_extra_key_urls()
        self.setup_extra_sources()
        self.update()

    def setup_extra_keys(self):
        for key in self.extra_keys:
            self.add_key(key)

    def setup_extra_key_urls(self):
        for key_url in self.extra_key_urls:
            self.add_key_url(key_url)

    def setup_extra_sources(self):
        for slug, sources in self.extra_sources.items():
            self.add_sources(slug, sources)

    def install_dpkg_packages(self):
        for package in self.dpkg_packages:
            self.hosts.sudo(wget(package))
            self.hosts.sudo("dpkg -i '%s'" % esc1(package.split('/')[-1]))
