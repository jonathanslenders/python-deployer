import re

class NetworkInterface(object):
    def __init__(self, name='eth0'):
        self.name = name
        self.ip = None

    def __repr__(self):
        return 'NetworkInterface(name=%r, ip=%r)' % (self.name, self.ip)


def parse_ifconfig_output(output, only_active_interfaces=True):
    """
    Parse the output of an `ifconfig` command and return a list of
    NetworkInterface objects.
    """
    interfaces = []
    current_interface = None

    for l in output.split('\n'):
        if l:
            # At any line starting with eth0, lo, tap7, etc..
            # Start a new interface.
            if not l[0].isspace():
                current_interface = NetworkInterface(l.split()[0].rstrip(':'))
                interfaces.append(current_interface)
                l = ' '.join(l.split()[1:])

            if current_interface:
                # If this line contains 'inet'
                for inet_addr in re.findall(r'inet (addr:)?(([0-9]*\.){3}[0-9]*)', l):
                    current_interface.ip = inet_addr[1]

    # Return only the interfaces that have an IP address.
    if only_active_interfaces:
        return filter(lambda i: i.ip, interfaces)
    else:
        return interfaces
