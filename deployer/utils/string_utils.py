
__all__ = (
        'esc1',
        'esc2',
        'indent',
)

def esc2(string):
    """
    Escape double quotes
    """
    return string.replace('"', r'\"')


def esc1(string):
    """
    Escape single quotes, mainly for use in shell commands. Single quotes
    are usually preferred above double quotes, because they never do shell
    expension inside. e.g.

    ::

        class HelloWorld(Node):
            def run(self):
                self.hosts.run("echo '%s'" % esc1("Here's some text"))
    """
    return string.replace("'", r"'\''")


def indent(string, prefix='    '):
    """
    Indent every line of this string.
    """
    return ''.join('%s%s\n' % (prefix, s) for s in string.split('\n'))

