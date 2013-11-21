from deployer.node import SimpleNode, dont_isolate_yet
from deployer.exceptions import ExecCommandFailed
from deployer.contrib.nodes.apt_get import AptGet


class Monitor(SimpleNode):
    """
    Various monitoring tools, like 'uptime'
    """
    class packages(AptGet):
        packages = ( 'htop',)


    def list_logged_in_users(self):
        self.host.run('w')

    def list_memory_usage(self):
        self.host.run('free -m')

    def htop(self):
        h = self.host

        with h.env('TERM', 'xterm'):
            try:
                h.run('htop')
            except ExecCommandFailed, e:
                h.sudo('apt-get install htop')
                h.run('htop')

    def pstree(self):
        with self.host.env('TERM', 'xterm'):
            self.host.run('pstree')

    def list_crons(self):
        try:
            #h.run('crontab -l')
            self.host.sudo('for user in $(cut -f1 -d: /etc/passwd); do echo $user; crontab -u $user -l || true; done')
        except ExecCommandFailed, e:
            print 'No cronjobs here...'

    @dont_isolate_yet
    def load(self):
        """
        Run 'uptime' on every host
        """
        print 'Load average the past 1, 5 and 15 minutes'
        for h in self.hosts:
            print '%40s: %s' % (h.slug, h.run("uptime | sed -e 's/^.*average://' ", interactive=False).strip())

    @dont_isolate_yet
    def list_hosts(self):
        """
        List all hosts with their IP addresses
        """
        print '%30s %20s %20s    %s' % ('name', 'address', 'hostname', 'ip address of eth0')
        print '%30s %20s %20s    %s' % ('----', '-------', '--------', '------------------')
        for host in self.hosts:
            try:
                print '%30s %20s %20s    %s' % (host.slug, host.address, host.hostname, host.get_ip_address())
            except Exception as e:
                print
                print e
                print
