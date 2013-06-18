from deployer.node import Node, SimpleNode, required_property, isolate_one_only
from deployer.utils import esc1
from deployer.contrib.nodes.apt_get import AptGet
from deployer.exceptions import ExecCommandFailed


class MySQL(Node):
    port = 3306


class MySQLClient(SimpleNode):
    """
    For simple Mysql operations, on a remote host.
    """
    hostname = required_property()
    username = required_property()
    password = required_property()
    database = required_property()

    def ensure_database_exists(self):
        """
        Create this database in MySQL if it wasn't created yet.
        """
        name = self.database
        try:
            # Try connect.
            self.hosts.run("echo 'CONNECT %s;' | /usr/bin/mysql --user '%s' --password='%s' --host '%s' " %
                    (name, esc1(self.username), esc1(self.password), esc1(self.hostname)))
        except ExecCommandFailed, e:
            # Connect raised error, so create it.
            self.hosts.run("echo 'CREATE DATABASE %s;' | /usr/bin/mysql --user '%s' --password='%s' --host '%s' " %
                    (name, esc1(self.username), esc1(self.password), esc1(self.hostname)))

    @isolate_one_only
    def restore_backup_from_url(self, url=None):
        if not url:
            url = self.console.input('Enter the URL of the backup location (an .sql.gz file)')
        self.hosts.run("curl '%s' | gunzip | /usr/bin/mysql --user '%s' --password='%s' --host '%s' '%s' " %
                    (esc1(url), esc1(self.username), esc1(self.password), esc1(self.hostname), esc1(self.database)))

    @isolate_one_only
    def shell(self):
        self.hosts.run("/usr/bin/mysql --user '%s' --password='%s' --host '%s' '%s' " %
                    (esc1(self.username), esc1(self.password), esc1(self.hostname), esc1(self.database)))


class PerconaToolkit(SimpleNode):
    class packages(AptGet):
        packages = ( 'percona-toolkit', )
        extra_keys = ( '1C4CBDCDCD2EFD2A', )
        extra_sources = { 'percona': [ 'deb http://repo.percona.com/apt lucid main' ] }

    def setup(self):
        # Install packages
        self.packages.setup_extra()
        self.packages.install()
