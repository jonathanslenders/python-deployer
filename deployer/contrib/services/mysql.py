from deployer.service import Service, required_property, isolate_host, isolate_one_only
from deployer.utils import esc1
from deployer.contrib.services.apt_get import AptGet
from deployer.console import input


class MySQL(Service):
    port = 3306


@isolate_host
class MySQLClient(Service):
    """
    For simple Mysql operations, on a remote host.
    """
    hostname = required_property()
    username = required_property()
    password = required_property()
    database = required_property()

    @isolate_one_only
    def restore_backup_from_url(self):
        backup_url = input('Enter the URL of the backup location (an .sql.gz file)')
        self.hosts.run("curl '%s' | gunzip | /usr/bin/mysql --user '%s' --password='%s' --host '%s' '%s' " %
                    (esc1(backup_url), esc1(self.username), esc1(self.password), esc1(self.hostname), esc1(self.database)))

    @isolate_one_only
    def shell(self):
        self.hosts.run("/usr/bin/mysql --user '%s' --password='%s' --host '%s' '%s' " %
                    (esc1(self.username), esc1(self.password), esc1(self.hostname), esc1(self.database)))


class PerconaToolkit(Service):
    class packages(AptGet):
        packages = ( 'percona-toolkit', )
        extra_keys = ( '1C4CBDCDCD2EFD2A', )
        extra_sources = { 'percona': [ 'deb http://repo.percona.com/apt lucid main' ] }

    def setup(self):
        # Install packages
        self.packages.setup_extra()
        self.packages.install()
