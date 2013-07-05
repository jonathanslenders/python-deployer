from pygments import highlight
from pygments.lexers import TextLexer, DiffLexer
from pygments.formatters import TerminalFormatter as Formatter

from deployer.node import SimpleNode, required_property, suppress_action_result
from deployer.utils import esc1

import difflib


class Config(SimpleNode):
    """
    Base class for all configuration files.
    """
    # Full path of the location where this config should be stored. (Start with slash)
    remote_path = required_property()

    # The textual content that should be saved in this place.
    content = required_property()

    # Pygments Lexer
    lexer = TextLexer

    use_sudo = True
    make_executable = False
    always_backup_existing_config = False

                # TODO: maybe we should make this True by default,
                #       but don't backup when the 'diff' is empty.

    def show_new_config(self):
        """
        Show the new configuration file. (What will be installed on 'setup')
        """
        print highlight(self.content, self.lexer(), Formatter())

    def show(self):
        """
        Show the currently installed configuration file.
        """
        print highlight(self.current_content, self.lexer(), Formatter())

    @property
    def current_content(self):
        """
        Return the content which currently exists in this file.
        """
        return self.host.open(self.remote_path, 'rb', use_sudo=True).read()

    @suppress_action_result
    def diff(self):
        """
        Show changes to be written to the file. (diff between the current and
        the new config.)
        """
        # Split new and existing content in lines
        current_content = self.current_content.splitlines(1)
        new_content = self.content.splitlines(1)

        # Call difflib
        diff = ''.join(difflib.unified_diff(current_content, new_content))
        print highlight(diff, DiffLexer(), Formatter())

        return diff

    @suppress_action_result
    def exists(self):
        """
        True when this config exists.
        """
        if self.host.exists(self.remote_path):
            print 'Yes, config exists already.'
            return True
        else:
            print 'Config doesn\'t exist yet'
            return False

    def changed(self):
        """
        Return True when there are configuration changes.
        (Or when the file does not yet exist)
        """
        if self.exists():
            return self.current_content != self.content
        else:
            return True

    def setup(self):
        """
        Install config on remote machines.
        """
        # Backup existing configuration
        if self.always_backup_existing_config:
            self.backup()

        self.host.open(self.remote_path, 'wb', use_sudo=self.use_sudo).write(self.content)

        if self.make_executable:
            self.host.sudo("chmod a+x '%s'" % esc1(self.host.expand_path(self.remote_path)))

    def backup(self):
        """
        Create a backup of this configuration file on the same host, in the same directory.
        """
        import datetime
        suffix = datetime.datetime.now().strftime('%Y-%m-%d--%H-%M-%S')
        self.host.sudo("test -f '%s' && cp --archive '%s' '%s.%s'" % (
                        esc1(self.remote_path), esc1(self.remote_path), esc1(self.remote_path), esc1(suffix)))

    def edit_in_vim(self):
        """
        Edit this configuration manually in Vim.
        """
        self.host.sudo("vim '%s'" % esc1(self.host.expand_path(self.remote_path)))
