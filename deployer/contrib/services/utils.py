from deployer.contrib.services.django import Django
from deployer.contrib.services.virtualenv import VirtualEnv
from deployer.service import Service, default_action, supress_action_result, isolate_host
from deployer.console import input

from pygments import highlight
from pygments.formatters import TerminalFormatter as Formatter
from pygments.lexers import DiffLexer

import difflib


@isolate_host
class Utils(Service):
    """
    Various tools, like 'set_hostname'
    """
    def set_hostname(self):
        """
        Set the hostname, according to the slug, given in the Host instance.
        """
        h = self.host

        if input('Do you really want to set the hostname for %s to %s' % (host.address, host.slug), answers=['y', 'n']) == 'y':
            h.sudo("echo '%s' > /etc/hostname" % host.slug)
            h.sudo("echo '127.0.0.1  %s' >> /etc/hosts" % host.slug)
            h.sudo("hostname -F /etc/hostname")

    def tail_deployment_history(self):
        self.host.run("test -f ~/.deployer/history && cat ~/.deployer/history")



class _Diff(Service):
    SERVICE_CLASSES = () # NOTE: Another reason for wrapping the class into a tuple here, is to
                         #       work around the Service.__metaclass__ behaviour which wraps
                         #       nested Service-classes

    def _print_output(self, output1, output2):
        output1 = output1.splitlines(1)
        output2 = output2.splitlines(1)

        diff = ''.join(difflib.unified_diff(output1, output2))

        print
        print 'Diff....'
        print

        print highlight(diff, DiffLexer(), Formatter())
        return diff

    @supress_action_result
    @default_action
    def diff(self, virtual_envs=None):
        from deployer.console import select_service

        def filter(service):
            # Only allow services of this kind
            return service.isinstance(self.SERVICE_CLASSES)

        s1 = select_service(self._pty, self.root, prompt=self.prompt, filter=filter)
        s2 = select_service(self._pty, self.root, prompt=self.prompt2, filter=filter)
        return self._print_output(self._call(s1), self._call(s2))


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
