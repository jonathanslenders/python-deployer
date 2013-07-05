
def esc2(string):
    """
    Escape double quotes
    """
    return string.replace('"', r'\"')


def esc1(string):
    """
    Escape single quotes

    If you want to get "Here's some text", it can be quoted as
    'Here'\''s some text' So, we have to lease the single quoted string, add
    an escaped quote, and enter the single quoted string again.
    """
    return string.replace("'", r"'\''")


def indent(string, prefix='    '):
    """
    Indent every line of this string.
    """
    return ''.join('%s%s\n' % (prefix, s) for s in string.split('\n'))

