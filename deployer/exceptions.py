
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
    Resolving of a Q object in a deployer Service failed.
    """
    def __init__(self, service, attr_name, query, inner_exception):
        self.service = service
        self.service_name = str(service.__class__)
        self.attr_name = attr_name
        self.query = query.__str__()
        self.inner_exception = inner_exception

        DeployerException.__init__(self, 'Running query %s:=%s on "%s" failed' %
                            (self.attr_name, self.query, self.service_name))
