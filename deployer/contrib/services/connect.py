from deployer.service import Service, isolate_host, default_action, isolate_one_only


@isolate_host
class Connect(Service):
    """
    Open SSH connection to host
    """
    @default_action
    @isolate_one_only # It does not make much sense to open interactive shells to all hosts at the same time.
    def with_host(self):
        self.host.start_interactive_shell()
        print

    @isolate_one_only
    def as_root(self):
        self.host.sudo('/bin/bash')
        print
