from deployer.utils import esc1


def wget(url, target=None):
    """
    Download file using wget
    """
    if target:
        return "wget '%s' --output-document '%s'" %  (esc1(url), esc1(target))
    else:
        return "wget '%s'" % esc1(url)
