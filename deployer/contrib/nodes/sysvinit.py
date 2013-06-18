from deployer.node import SimpleNode, required_property
from deployer.utils import esc1

class SysVInitService(SimpleNode):
    slug = required_property()
    no_pty = False

    def _make_command(command):
        def run(self):
            self.hosts.sudo("service '%s' %s" % (esc1(self.slug), command), interactive=not self.no_pty)
        return run

    stop = _make_command('stop')
    start = _make_command('start')
    status = _make_command('status')
    restart = _make_command('restart')
    reload = _make_command('reload')

    def install(self, runlevels='defaults', priority='20'):
        self.hosts.sudo("update-rc.d '%s' %s %s" % (esc1(self.slug), runlevels, priority))

    def uninstall(self):
        self.hosts.sudo("update-rc.d '%s' remove" % esc1(self.slug))
