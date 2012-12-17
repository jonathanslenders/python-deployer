from deployer.console import input
from deployer.contrib.services.apt_get import AptGet
from deployer.exceptions import ExecCommandFailed
from deployer.service import Service, default_action, isolate_host, isolate_one_only
from deployer.utils import esc1


@isolate_host
class Tmux(Service):
    """
    Open SSH connection to host
    """
    #url = 'http://downloads.sourceforge.net/project/tmux/tmux/tmux-1.6/tmux-1.6.tar.gz'
    url = 'http://downloads.sourceforge.net/tmux/tmux-1.7.tar.gz'

    @default_action
    @isolate_one_only # It does not make much sense to open interactive shells to all hosts at the same time.
    def attach(self):
        # Test whether tmux is installed
        try:
            self.host.run('which tmux > /dev/null')
        except ExecCommandFailed:
            # Not installed -> ask for compiling tmux
            if input('Tmux binary not found. Do you want to compile tmux on %s?' % self.host.slug, answers=['y', 'n']) == 'y':
                setup = self.initialize_service(TmuxSetup, host=self.host)
                setup.install()
            else:
                return

        # Attach or start tmux
        self.host.run('tmux attach-session || tmux')


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
