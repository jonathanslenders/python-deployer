import re

class NetworkInterface(object):
    def __init__(self, name='eth0'):
        self.name = name
        self.ip = None

    def __repr__(self):
        return 'NetworkInterface(name=%r, ip=%r)' % (self.name, self.ip)


class IfConfig(object):
    def __init__(self):
        self.interfaces = []

    def __repr__(self):
        return 'IfConfig(interfaces=%r)' % self.interfaces

    def get_interface(self, name):
        for i in self.interfaces:
            if i.name == name:
                return i
        raise AttributeError

    def get_address(self, ip):
        for i in self.interfaces:
            if i.ip == ip:
                return i
        raise AttributeError


def parse_ifconfig_output(output, only_active_interfaces=True):
    """
    Parse the output of an `ifconfig` command.

    :returns: A list of ``NetworkInterface`` objects.
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
                    current_interface.ip = inet_addr[1]

    # Return only the interfaces that have an IP address.
    if only_active_interfaces:
        ifconfig.interfaces = filter(lambda i: i.ip, ifconfig.interfaces)

    return ifconfig
