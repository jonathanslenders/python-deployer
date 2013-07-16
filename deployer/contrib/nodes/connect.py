from deployer.node import SimpleNode, isolate_one_only


class Connect(SimpleNode):
    """
    Open SSH connection to host
    """
    @property
    def initial_input(self):
        # Override this one in order to create a connect statement
        # which does 'cd' to a certain directory, activates a virtualenv,
        # or executes any other arbitrary command in the shell before handing
        # over control to the user.
        return None

    @isolate_one_only # It does not make much sense to open interactive shells to all hosts at the same time.
    def with_host(self):
        self.host.start_interactive_shell(initial_input=self.initial_input)
        print

    @isolate_one_only
    def as_root(self):
        self.host.sudo('/bin/bash')
        print

    __call__ = with_host
