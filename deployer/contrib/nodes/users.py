from deployer.node import SimpleNode, required_property
from deployer.utils import esc1
from deployer.query import Q

class User(SimpleNode):
    """
    Unix/Linux user management.
    """
    username = required_property()
    groupname = Q.username
    has_home_directory = True
    home_directory_base = None
    shell = '/bin/bash'

    def create(self):
        """
        Create this user and home directory.
        (Does not fail when the user or directory already exists.)
        """
        if self.exists():
            return

        useradd_args = []
        useradd_args.append("'%s'" % esc1(self.username))
        useradd_args.append("-s '%s'" % self.shell)
        if self.has_home_directory:
            useradd_args.append('-m')
            if self.home_directory_base:
                useradd_args.append("-b '%s'" % self.home_directory_base)
        else:
            useradd_args.append('-M')

        # Group
        if self.username == self.groupname:
            useradd_args.append('-U')
        else:
            if self.groupname:
                self.host.sudo("grep '%s' /etc/group || groupadd '%s'" % esc1(self.groupname), esc1(self.groupname))
                useradd_args.append("-g '%s'" % esc1(self.groupname))

        self.host.sudo("useradd " + " ".join(useradd_args))

    def exists(self):
        """
        Return true when this user account was already created.
        """
        try:
            self.host.sudo("grep '%s' /etc/passwd" % self.username)
            return True
        except:
            return False
