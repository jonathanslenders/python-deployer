from deployer.node import SimpleNode, Node
import termcolor

from deployer.inspection.inspector import Inspector


class AnalyseHost(SimpleNode):
    """
    Analyze a host and find out what it's used for.
    """
    def analyise(self):
        """
        Discover what a host is used for, which role mappings it has for every
        node.
        """
        print termcolor.colored('Showing node::role for every match of %s' % self.host.slug, 'cyan')

        def process_node(node):
            # Gather roles which contain this host in the current node.
            roles = []
            for role in node.hosts.roles:
                if self.host in node.hosts.filter(role):
                    roles.append(role)

            # If roles were found, print result
            if roles:
                print '.'.join(Inspector(node).get_path()), termcolor.colored(' :: ', 'cyan'), termcolor.colored(', '.join(roles), 'yellow')

            for childnode in Inspector(node).get_childnodes(verify_parent=True):
                process_node(childnode)

        process_node(Inspector(self).get_root())
    __call__ = analyise


class Inspection(Node):
    """
    Inspection of all services
    """
    except_peer_services = [ ]

    def print_everything(self):
        """
        Example command which prints all services with their actions
        """
        def print_service(service):
            print
            print '====[ %s ]==== ' % service.__repr__(path_only=True)
            print

            print 'Actions:'
            for name, action in service.get_actions():
                print ' - ', name, action
            print

            for name, subnode in service.get_subnodes():
                print_service(subnode)

        print_service(Inspector(self).get_root())


    def global_status(self):
        """
        Sanity check.
        This will browse all services for a 'status' method and run it.
        """
        def process_service(service):
            print service.__repr__(path_only=True)

            for name, action in service.get_actions():
                if name == 'status':
                    try:
                        action()
                    except Exception, e:
                        print 'Failed: ', e.message

            for name, subnode in service.get_subnodes():
                process_service(subnode)

        process_service(Inspector(self).get_root())
