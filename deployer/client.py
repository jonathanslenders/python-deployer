#!/usr/bin/env python

import getopt
import sys
import getpass

from deployer.run.socket_client import start as start_client
from deployer.run.socket_client import list_sessions
from deployer.run.socket_server import start as start_server
from deployer.run.standalone_shell import start as start_standalone

from deployer.contrib.default_config import example_settings


def start(root_service):
    """
    Client startup point.
    """
    cd_path = None
    socket_name = ''
    interactive = True
    single_threaded = False
    logfile = None
    socket_server = False

    def print_usage():
        print 'Usage:'
        print '    ./client.py [-h|--help] [ -c|--connect "socket number" ] [ -p|--path "path" ] [ -l | --list-sessions ]'
        print '                [--interactive|--non-interactive ] [ -s|--single-threaded ] [ -m|--multithreaded ]'
        print '                [--log] [--server]'

    # Parse command line arguments.
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hp:c:lsm', ['help', 'path=', 'connect=', 'list-sessions',
                            'interactive', 'non-interactive', 'single-threaded', 'multithreaded', 'log=', 'server'])
    except getopt.GetoptError, err:
        print str(err)
        print_usage()
        sys.exit(2)

    for o, a in opts:
        if o in ('-h', '--help'):
            print_usage()
            sys.exit()

        elif o in ('-l', '--list-sessions',):
            list_sessions()
            sys.exit()

        elif o in ('-c', '--connect'):
            socket_name = a

        elif o in ('-p', '--path'):
            cd_path = a.split('.')

        elif o in ('--non-interactive', ):
            interactive = False

        elif o in ('--interactive', ):
            interactive = True

        elif o in ('-s', '--single-threaded'):
            single_threaded = True

        elif o in ('-m', '--multithreaded'):
            single_threaded = False

        elif o in ('--log',):
            logfile = a

        elif o in ('--server',):
            socket_server = True

        else:
            print 'Unknown option: %s' % o
            sys.exit(2)

    if socket_server:
        # == Socket server ==
        socket_name = start_server(root_service, daemonized=False, shutdown_on_last_disconnect=False, interactive=interactive, logfile=logfile)
    elif single_threaded:
        # == Single threaded ==
        start_standalone(root_service, interactive=interactive, cd_path=cd_path, logfile=a)
    else:
        # == Multithreaded ==

        # If no socket has been given. Start a daemonized server in the
        # background, and use that socket instead.
        if not socket_name:
            socket_name = start_server(root_service, daemonized=True, shutdown_on_last_disconnect=True, interactive=interactive, logfile=logfile)

        # The socket path can be an absolute path, or an integer.
        if not socket_name.startswith('/'):
            socket_name = '/tmp/deployer.sock.%s.%s' % (getpass.getuser(), socket_name)

        start_client(socket_name, cd_path)


if __name__ == '__main__':
    start(root_service=example_settings)
