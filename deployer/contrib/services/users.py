from deployer.service import Service, isolate_host
from deployer.utils import esc1


@isolate_host
class User(Service):
    """
    Unix/Linux user management.
    """
    username = 'username'
    home_directory = '/home/username'
    shell = '/bin/bash'

    def create(self):
        """
        Create this user and home directory.
        (Does not fail when the user or directory already exists.)
        """
        username = esc1(self.username)
        home_directory = esc1(self.home_directory)
        shell = esc1(self.shell)

        # Create user if he doesn't exists yet
        self.hosts.sudo("grep '%s' /etc/passwd || useradd '%s' -d '%s' -s '%s' " % (username, username, home_directory, shell))

        # Create home directory, and make this user the owner
        self.hosts.sudo("mkdir -p '%s' " % home_directory)
        self.hosts.sudo("chown %s:%s '%s' " % (username, username, self.home_directory))

    def exists(self):
        """
        Return true when this user account was already created.
        """
        try:
            self.hosts.sudo("grep '%s' /etc/passwd" % self.username)
            return True
        except:
            return False
