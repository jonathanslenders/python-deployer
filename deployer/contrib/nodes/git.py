from deployer.exceptions import ExecCommandFailed
from deployer.node import Node, SimpleNode, SimpleNodeBase, dont_isolate_yet, required_property
from deployer.utils import esc1
import termcolor

__all__ = ('Git', 'GitOverview' )


class GitBase(SimpleNodeBase):
    _default_commands = {
        'branch': 'branch',
        'describe': 'describe',
        'diff': 'diff',
        'log': 'log',
        'pull': 'pull',
        'reset': 'reset --hard',
        'show': 'show',
        'show_oneline': 'show --oneline|head -n 1',
        'stash': 'stash',
        'stash_list': 'stash list',
        'stash_pop': 'stash pop',
        'stash_clear': 'stash clear',
        'status': 'status',
        'version': 'version',
        'whatchanged': 'whatchanged',
        'head_sha': 'rev-parse HEAD',
    }

    _ignore_exit_status = [ 'show', 'whatchanged' ] # These are displayed through lesspipe, and would return 141 when 'q' was pressed.

    def __new__(cls, name, bases, attrs):
        # Extra git commands
        commands = attrs.get('commands', { })

        for cmd_name, command in cls._default_commands.items() + commands.items():
            attrs[cmd_name] = cls._create_git_command(command,
                                        ignore_exit_status=command in cls._ignore_exit_status)

        return SimpleNodeBase.__new__(cls, name, bases, attrs)

    @staticmethod
    def _create_git_command(command, ignore_exit_status=False):
        def run(self):
            with self.host.cd(self.repository_location):
                return self.host.run('git %s' % command, ignore_exit_status=ignore_exit_status)
        return run


class Git(SimpleNode):
    """
    Manage the git checkout of a project
    """
    __metaclass__ = GitBase

    repository = required_property()
    repository_location = required_property()
    default_revision = 'master'

    commands = { } # Extra git commands. Map function name to git command.

    @dont_isolate_yet
    def checkout(self, commit=None):
        # NOTE: this public 'checkout'-method uses @dont_isolate_yet, so that
        # in case of a parrallel checkout, we only ask once for the commit
        # name, and fork only to several threads after calling '_checkout'.

        # If no commit was given, ask for commit.
        if not commit:
            commit = self.console.input('Git commit', default=self.default_revision)
            if not commit: raise Exception('No commit given')

        self._checkout(commit)

    def _checkout(self, commit):
        """
        This will either clone or checkout the given commit. Changes in the
        repository are always stashed before checking out, and stash-popped
        afterwards.
        """
        # Checkout on every host.
        host = self.host
        existed = host.exists(self.repository_location)

        if not existed:
            # Do a new checkout
            host.run('git clone --recursive %s %s' % (self.repository, self.repository_location))

        with host.cd(self.repository_location):
            host.run('git fetch --all --prune')

            # Stash
            if existed:
                host.run('git stash')

            # Checkout
            try:
                host.run("git checkout '%s'" % esc1(commit))
                host.run("git submodule update --init") # Also load submodules.
            finally:
                # Pop stash
                try:
                    if existed:
                        host.run('git stash pop 2>&1', interactive=False) # will fail when checkout had no local changes
                except ExecCommandFailed, e:
                    result = e.result
                    if result.strip() not in ('Nothing to apply', 'No stash found.'):
                        print result
                        if not self.console.confirm('Should we continue?', default=True):
                            raise Exception('Problem with popping your stash, please check logs and try again.')

class GitOverview(Node):
    """
    Show a nice readable overview of all the git checkouts of all the services in the tree.
    """
    def show(self):
        # Preparing results.
        result = { }
        def walk(service):
            if service.isinstance(Git):
                # In case that we have more hosts in this git checkout, call
                # it for every individual isolation.
                if service.is_isolated:
                    result[service] = { i.service.host.slug: service.show_oneline() }
                else:
                    result[service] = { i.service.host.slug: i.service.show_oneline() for i in service.get_isolations() }

            for name, s in service.get_subservices():
                if s.parent == service: # Make sure that we don't walk in loops (back to parent nodes.)
                    walk(s)
        walk(self.root)

        # Show results
        print
        for service, data in result.items():
            print termcolor.colored(service.__repr__(path_only=True), service.get_group().color)

            for host_slug, git_output in data.items():
                print '      %-40s %s' % (termcolor.colored(host_slug, 'green'), git_output.strip())

    __call__ = show
