from deployer.service import Service, default_action


class SCP(Service):
    """
    Secure copy between hosts.
    """
    @default_action
    def scp(self):
        # TODO: Add progress bar for large files.

        host1 = self.console.input('Host 1')
        host2 = self.console.input('Host 2')
        path1 = self.console.input('Path 1')
        path2 = self.console.input('Path 2')

        host1 = self.hosts.get_from_slug(host1)
        host2 = self.hosts.get_from_slug(host2)

        data = host1.open(path1, 'r').read()
        host2.open(path2, 'w').write(data)

    # TODO: download action, for downloading files to the deployment server.
