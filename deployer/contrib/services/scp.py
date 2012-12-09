from deployer.service import Service, default_action
from deployer.console import input


class SCP(Service):
    """
    Secure copy between hosts.
    """
    @default_action
    def scp(env):
        # TODO: - make from 'host1' and 'host2' parameters, and add
        #         autocompletion for both
        #
        #       - Add progress bar for large files.

        host1 = input('Host 1')
        host2 = input('Host 2')
        path1 = input('Path 1')
        path2 = input('Path 2')

        host1 = env.hosts.get_from_slug(host1)
        host2 = env.hosts.get_from_slug(host2)

        data = host1.open(path1, 'r').read()
        host2.open(path2, 'w').write(data)

    #scp.autocomplete = lambda env, text: [ h.slug for h in env.hosts if h.slug.startswith(text) ]


    # TODO: download action, for downloading files to the deployment server.
