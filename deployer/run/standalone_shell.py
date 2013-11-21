#!/usr/bin/env python

from deployer.loggers import LoggerInterface
from deployer.loggers.default import DefaultLogger
from deployer.exceptions import ActionException
from deployer.pseudo_terminal import Pty
from deployer.shell import Shell

from contextlib import nested
from setproctitle import setproctitle

import logging
import os
import signal
import sys


__all__ = ('start',)


class StandaloneShell(Shell):
    """
    You can inherit this shell, add your extension, and pass that class
    to the start method below.
    """
    @property
    def extensions(self):
        return { }


def start(root_node, interactive=True, cd_path=None, logfile=None,
                action_name=None, parameters=None, shell=StandaloneShell,
                extra_loggers=None, open_scp_shell=False):
    """
    Start the deployment shell in standalone modus. (No parrallel execution,
    no server/client. Just one interface, and everything sequential.)
    """
    parameters = parameters or []

    # Enable logging
    if logfile:
        logging.basicConfig(filename=logfile, level=logging.DEBUG)

    # Make sure that stdin and stdout are unbuffered
    # The alternative is to start Python with the -u option
    sys.stdin = os.fdopen(sys.stdin.fileno(), 'r', 0)
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

    # Create Pty object
    pty = Pty(sys.stdin, sys.stdout, interactive=interactive)

    def sigwinch_handler(n, frame):
        pty.trigger_resize()
    signal.signal(signal.SIGWINCH, sigwinch_handler)

    # Initialize root node
    root_node = root_node()

    # Set process title
    setproctitle('deploy:%s run -s' % root_node.__class__.__name__)

    # Loggers
    in_shell_logger = DefaultLogger(print_group=False)

    logger_interface = LoggerInterface()
    extra_loggers = extra_loggers or []

    with logger_interface.attach_in_block(in_shell_logger):
        with nested(* [logger_interface.attach_in_block(l) for l in extra_loggers]):
            # Create shell
            print 'Running single threaded shell...'
            shell = shell(root_node, pty, logger_interface)
            if cd_path is not None:
                shell.cd(cd_path)

            if action_name and open_scp_shell:
                raise Exception("Don't provide 'action_name' and 'open_scp_shell' at the same time")

            if open_scp_shell:
                shell.open_scp_shell()

            elif action_name:
                try:
                    return shell.run_action(action_name, *parameters)
                except ActionException as e:
                    sys.exit(1)
                except:
                    import traceback
                    traceback.print_exc()
                    sys.exit(1)

            else:
                shell.cmdloop()
