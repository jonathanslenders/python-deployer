import re

__all__ = ('parse_ifconfig_output', 'IfConfig', 'NetworkInterface')


class NetworkInterface(object):
    """
    Information about a single network interface.
    """
    def __init__(self, name='eth0'):
        self._name = name
        self._ip = None

    @property
    def name(self):
        """
        Name of the network interface. e.g. "eth0".
        """
        return self._name

    @property
    def ip(self):
        """
        IP address of the network interface. e.g. "127.0.0.1"
        """
        return self._ip

    def __repr__(self):
        return 'NetworkInterface(name=%r, ip=%r)' % (self.name, self.ip)


class IfConfig(object):
    """
    Container for the network settings, found by `ifconfig`.
    This contains a list of :class:`NetworkInterface`.
    """
    def __init__(self):
        self._interfaces = []

    @property
    def interfaces(self):
        """
        List of all :class:`NetworkInterface` objects.
        """
        return self._interfaces

    def __repr__(self):
        return 'IfConfig(interfaces=%r)' % self.interfaces

    def get_interface(self, name):
        """
        Return the :class:`NetworkInterface` object, given an interface name
        (e.g. "eth0") or raise `AttributeError`.
        """
        for i in self.interfaces:
            if i.name == name:
                return i
        raise AttributeError

    def get_address(self, ip):
        """
        Return the :class:`NetworkInterface` object, given an IP addres
        (e.g. "127.0.0.1") or raise `AttributeError`.
        """
        for i in self.interfaces:
            if i.ip == ip:
                return i
        raise AttributeError


def parse_ifconfig_output(output, only_active_interfaces=True):
    """
    Parse the output of an `ifconfig` command.

    :returns: A list of :class:`IfConfig` objects.

    Example usage:
    ::
        ifconfig = parse_ifconfig_output(host.run('ifconfig'))
        interface = ifconfig.get_interface('eth0')
        print interface.ip
    """
    ifconfig = IfConfig()
    current_interface = None

    for l in output.split('\n'):
        if l:
            # At any line starting with eth0, lo, tap7, etc..
            # Start a new interface.
            if not l[0].isspace():
                current_interface = NetworkInterface(l.split()[0].rstrip(':'))
                ifconfig.interfaces.append(current_interface)
                l = ' '.join(l.split()[1:])

            if current_interface:
                # If this line contains 'inet'
                for inet_addr in re.findall(r'inet (addr:)?(([0-9]*\.){3}[0-9]*)', l):
                    current_interface._ip = inet_addr[1]

    # Return only the interfaces that have an IP address.
    if only_active_interfaces:
        ifconfig._interfaces = filter(lambda i: i.ip, ifconfig._interfaces)

    return ifconfig
