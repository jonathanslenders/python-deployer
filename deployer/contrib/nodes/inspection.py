from deployer.inspection.inspector import Inspector
from deployer.node import SimpleNode, Node

import termcolor


class AnalyseHost(SimpleNode):
    """
    Analyze a host and find out what it's used for.
    """
    def analyise(self):
        """
        Discover what a host is used for, which role mappings it has for every
        node.
        """
        with self.console.progress_bar('Looking for nodes') as progress_bar:
            print termcolor.colored('Showing node::role for every match of %s' % self.host.slug, 'cyan')

            def process_node(node):
                # Gather roles which contain this host in the current node.
                roles = []
                for role in node.hosts.roles:
                    progress_bar.next()
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
        Example command which prints all nodes with their actions
        """
        def print_node(node):
            print
            print '====[ %s ]==== ' % node.__repr__(path_only=True)
            print

            print 'Actions:'
            for name, action in node.get_actions():
                print ' - ', name, action
            print

            for child in node.get_childnodes():
                print_node(child)

        print_node(Inspector(self).get_root())


    def global_status(self):
        """
        Sanity check.
        This will browse all nodes for a 'status' method and run it.
        """
        def process_node(node):
            print node.__repr__()

            for name, action in node.get_actions():
                if name == 'status':
                    try:
                        action()
                    except Exception as e:
                        print 'Failed: ', e.message

            for name, subnode in node.get_subnodes():
                process_node(subnode)

        process_node(Inspector(self).get_root())
