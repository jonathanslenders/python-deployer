from deployer.host import LocalHost
from deployer.host import SSHHost

import os
import getpass


class LocalHost1(LocalHost):
    # Act as another host then localhost
    slug = 'localhost1'

class LocalHost2(LocalHost):
    # Act as another host then localhost
    slug = 'localhost2'

class LocalHost3(LocalHost):
    # Act as another host then localhost
    slug = 'localhost3'

class LocalHost4(LocalHost):
    # Act as another host then localhost
    slug = 'localhost4'

class LocalHost5(LocalHost):
    # Act as another host then localhost
    slug = 'localhost5'


class LocalSSHHost1(SSHHost):
    """
    Passwordless SSH connection to localhost.

    To generate the certificate, do:

    $ ssh-keygen -f ~/.ssh/id_rsa_local -N ""
    $ cat id_rsa_local.pub >> authorized_keys
    """
    key_filename = os.path.expanduser('~/.ssh/id_rsa_local')
    address = 'localhost'
    username = getpass.getuser()
    slug = 'local-ssh-1'

class LocalSSHHost2(LocalSSHHost1):
    slug = 'local-ssh-2'

class LocalSSHHost3(LocalSSHHost1):
    slug = 'local-ssh-3'

class LocalSSHHost4(LocalSSHHost1):
    slug = 'local-ssh-4'

class LocalSSHHost5(LocalSSHHost1):
    slug = 'local-ssh-5'
