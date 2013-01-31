from deployer.utils import esc1

def wget(url, target=None):
    """
    Download file using wget
    """
    if target:
        return "wget '%s' --output-document '%s'" %  (esc1(url), esc1(target))
    else:
        return "wget '%s'" % esc1(url)

def bashrc_append(line):
    """
    Create a command which appends something to .bashrc if this line was not yet added before.
    """
    return "grep '%s' ~/.bashrc || echo '%s' >> ~/.bashrc" % (esc1(line), esc1(line))
