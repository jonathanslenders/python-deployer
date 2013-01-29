from deployer.host import SSHHost, LocalHost

import os.path


class VagrantHost(SSHHost):
    """
    Virtual machine, created by the Vagrant wrappers.
    http://www.vagrantup.com/

    TOOD:
    - not yet for multiple-vm environments
    - Probably only works when host_machine is Localhost (no ssh proxy.)
    """
    # Directory which contains the Vagrantfile.
    vagrant_environment = '~'

    # Host machine on which the VirtualBox instance in running.
    host_machine = LocalHost


    @property
    def slug(self):
        return 'vagrant-%s' % os.path.split(self.vagrant_environment)[1]

    @property
    def address(self):
        return self._get_ssh_property('HostName')

    @property
    def port(self):
        return int(self._get_ssh_property('Port'))

    @property
    def username(self):
        return self._get_ssh_property('User')

    @property
    def key_filename(self):
        return self._get_ssh_property('IdentityFile')

    def _get_ssh_property(self, key):
        """
        Run "vagrant ssh-config", and retrieve property.
        """
        if not hasattr(self, '_ssh_config'):
            host = self.host_machine()

            with host.cd(self.vagrant_environment):
                self._ssh_config = host._run_silent('vagrant ssh-config')

        for line in self._ssh_config.splitlines():
            k, v = line.strip().split(None, 1)

            if k == key:
                return v
