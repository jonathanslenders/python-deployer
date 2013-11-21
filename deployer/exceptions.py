
class DeployerException(Exception):
    """
    Base exception class.
    """
    pass


class ExecCommandFailed(DeployerException):
    """
    Execution of a run() or sudo() call on a host failed.
    """
    def __init__(self, command, host, use_sudo, status_code, result=None):
        self.command = command
        self.use_sudo = use_sudo
        self.host = host
        self.status_code = status_code
        self.result = result

        DeployerException.__init__(self, 'Executing "%s" on "%s" failed with status code: %s' %
                    (command, host.slug, status_code))


class QueryException(DeployerException):
    """
    Resolving of a Q object in a deployer Node failed.
    """
    def __init__(self, node, attr_name, query, inner_exception):
        self.node = node
        self.attr_name = attr_name
        self.query = query
        self.inner_exception = inner_exception

        DeployerException.__init__(self, 'Running query %s:=%r on "%s" failed' %
                            (self.attr_name, self.query, repr(self.node)))

class ActionException(DeployerException):
    """
    When an action fails.
    """
    def __init__(self, inner_exception, traceback):
        self.inner_exception = inner_exception
        self.traceback = traceback
