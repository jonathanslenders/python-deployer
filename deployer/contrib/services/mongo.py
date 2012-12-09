from deployer.service import Service, map_roles, required_property, isolate_host
from deployer.contrib.services.apt_get import AptGet


@isolate_host
class Mongo(Service):
    """
    Tools for MongoDB (key/value storage)
    """
    class packages(AptGet):
        packages = ('mongodb', )

    def setup(self):
        self.packages.install()

    def shell(self):
        self.hosts.run('mongo')

    def stat(self):
        self.hosts.run('mongostat')

    def show_databases(self):
        self.hosts.run('echo "show dbs" | mongo')
