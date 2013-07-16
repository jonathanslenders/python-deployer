from deployer.contrib.nodes.django import Django
from deployer.contrib.nodes.virtualenv import VirtualEnv
from deployer.node import SimpleNode, Node, suppress_action_result

from pygments import highlight
from pygments.formatters import TerminalFormatter as Formatter
from pygments.lexers import DiffLexer

import difflib


class Utils(SimpleNode):
    """
    Various tools, like 'set_hostname'
    """
    def set_hostname(self):
        """
        Set the hostname, according to the slug, given in the Host instance.
        """
        host = self.host

        if self.console.confirm('Do you really want to set the hostname for %s to %s' % (host.address, host.slug)):
            host.sudo("echo '%s' > /etc/hostname" % host.slug)
            host.sudo("echo '127.0.0.1  %s' >> /etc/hosts" % host.slug)
            host.sudo("hostname -F /etc/hostname")

    def tail_deployment_history(self):
        self.host.run("test -f ~/.deployer/history && cat ~/.deployer/history")



class _Diff(Node):
    SERVICE_CLASSES = () # NOTE: Another reason for wrapping the class into a tuple here, is to
                         #       work around the Node.__metaclass__ behaviour which wraps
                         #       nested Node-classes

    def _print_output(self, output1, output2):
        output1 = output1.splitlines(1)
        output2 = output2.splitlines(1)

        diff = ''.join(difflib.unified_diff(output1, output2))

        print
        print 'Diff....'
        print

        print highlight(diff, DiffLexer(), Formatter())
        return diff

    @suppress_action_result
    def diff(self, virtual_envs=None):
        def filter(service):
            # Only allow services of this kind
            return service.isinstance(self.SERVICE_CLASSES)

        s1 = self.console.select_node(self.root, prompt=self.prompt, filter=filter)
        s2 = self.console.select_node(self.root, prompt=self.prompt2, filter=filter)
        return self._print_output(self._call(s1), self._call(s2))
    __call__ = diff


class VirtualEnvDiff(_Diff):
    """
    Run a diff between to virtual env instances
    """
    SERVICE_CLASSES = (VirtualEnv, )
    prompt = 'Select a Virtualenv service'
    prompt2 = 'Select a second Virtualenv'

    def _call(self, service):
        return service.freeze()


class DjangoMigrationsDiff(_Diff):
    """
    Run a diff on the Django `migrate --list` command.
    """
    SERVICE_CLASSES = (Django, )
    prompt = 'Select a Django service'
    prompt2 = 'Select a second Django service'

    def _call(self, service):
        return service.list_migrations()
