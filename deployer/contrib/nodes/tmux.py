from deployer.contrib.nodes.apt_get import AptGet
from deployer.exceptions import ExecCommandFailed
from deployer.node import SimpleNode, isolate_one_only
from deployer.utils import esc1


class Tmux(SimpleNode):
    """
    Open SSH connection to host
    """
    url = 'http://downloads.sourceforge.net/tmux/tmux-1.8.tar.gz'

    @isolate_one_only # It does not make much sense to open interactive shells to all hosts at the same time.
    def attach(self):
        # Test whether tmux is installed
        try:
            self.host.run('which tmux > /dev/null')
        except ExecCommandFailed:
            # Not installed -> ask for compiling tmux
            if self.console.confirm('Tmux binary not found. Do you want to compile tmux on %s?' % self.host.slug, default=True):
                setup = self.initialize_service(TmuxSetup, host=self.host)
                setup.install()
            else:
                return

        # Attach or start tmux
        self.host.run('tmux attach-session || tmux')

    __call__ = attach

class TmuxSetup(AptGet):
    packages = ('libevent-dev', 'libncurses-dev', )

    def install(self):
        AptGet.install(self)

        for h in self.hosts:
            with h.cd('/tmp'):
                # Download tmux in /tmp
                self.hosts.run("wget '%s' -O /tmp/tmux.tgz" % esc1(Tmux.url))
                self.hosts.run("tar xvzf tmux.tgz")

                with h.cd('tmux-1.*'):
                    # ./configure; make; sudo make install
                    self.hosts.run("./configure")
                    self.hosts.run("make")
                    self.hosts.sudo("make install")
