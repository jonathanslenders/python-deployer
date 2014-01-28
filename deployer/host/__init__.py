
"""
This module contains the immediate wrappers around the remote hosts and their
terminals. It's possible to run commands on a host directly by using these
classes. As an end-user of this library however, you will call the methods of
:class:`SSHHost <.ssh.SSHHost>` and :class:`LocalHost <.local.LocalHost>`
through :class:`HostsContainer <deployer.host_container.HostsContainer>`, the
host proxy of a :class:`Node <deployer.node.base.Node>`.
"""

from .base import *
from .ssh import *
from .local import *
