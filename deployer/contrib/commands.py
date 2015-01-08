from deployer.utils import esc1

def wget(url, target=None, pipe=None):
    """
    Download file using wget
    """
    command = "wget %s" % esc1(url)
    if pipe:
        target = '-'
    if target:
        command += " --output-document '%s'" % esc1(target)
    if pipe:
        command += " | " + pipe
    return command

def bashrc_append(line):
    """
    Create a command which appends something to .bashrc if this line was not yet added before.
    """
    return "grep '%s' ~/.bashrc || echo '%s' >> ~/.bashrc" % (esc1(line), esc1(line))
