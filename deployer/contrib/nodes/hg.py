from deployer.node import SimpleNode, required_property, dont_isolate_yet, SimpleNodeBase
from deployer.utils import esc1

class HgBase(SimpleNodeBase):
    _default_commands = {
        'id': 'id',
        'log': 'log',
        'status': 'status',
        'summary': 'summary',
        'version': 'version',
    }

    def __new__(cls, name, bases, attrs):
        # Extra hg commands
        commands = attrs.get('commands', { })

        for cmd_name, command in cls._default_commands.items() + commands.items():
            attrs[cmd_name] = cls._create_hg_command(command)

        return SimpleNodeBase.__new__(cls, name, bases, attrs)

    @staticmethod
    def _create_hg_command(command):
        def run(self):
            with self.host.cd(self.repository_location):
                return self.host.run('hg %s' % command)
        return run

class Hg(SimpleNode):
    """
    Mercurial repository.
    """
    __metaclass__ = HgBase

    repository = required_property()
    repository_location = required_property()
    default_changeset = 'default'

    commands = { } # Extra hg commands. Map function name to hg command.

    @dont_isolate_yet
    def checkout(self, changeset=None):
        if not changeset:
            commit = self.console.input('Hg changeset', default=self.default_changeset)
            if not commit: raise Exception('No changeset given')

        self._checkout(changeset)

    def _checkout(self, changeset):
        # Clone the fist time
        existed = self.host.exists(self.repository_location)
        if not existed:
            self.host.run("hg clone '%s' '%s'" % (esc1(self.repository), esc1(self.repository_location)))

        # Checkout
        with self.host.cd(self.repository_location):
            self.host.run("hg checkout '%s'" % esc1(changeset))
