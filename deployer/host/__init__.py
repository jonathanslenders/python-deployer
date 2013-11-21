
__doc__ = \
"""
This module contains the immediate wrappers around the remote hosts and their
terminals. It's possible to run commands on a host directly by using these
classes. As an end-user of this library however, you will call the methods of
:class:`SSHHost` and :class:`LocalHost` through
:class:`deployer.host_container.HostsContainer`, the host proxy of a
:class:`deployer.node.Node`.
"""

from .base import *
from .ssh import *
from .local import *
