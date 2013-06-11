#!/usr/bin/env python

from deployer.cli import NoSubHandler
from deployer.loggers import Logger, CliActionCallback
from deployer.loggers import LoggerInterface
from deployer.loggers.default import DefaultLogger, IndentedDefaultLogger
from deployer.loggers.trace import TracePrinter
from deployer.pty import Pty
from deployer.shell import Shell, ShellHandler, GroupHandler, BuiltinType

import codecs
import logging
import os
import random
import signal
import string
import sys
import termcolor
import time


__all__ = ('start',)


# Data structures for history

class HistoryLogger(Logger):
    """
    Small logger for capturing the history.
    """
    def __init__(self):
        # Keep history of events
        self.history = []

    def log_cli_action(self, action_entry):
        self.history.append(action_entry)
        return CliActionCallback() # Dummy callback


# Shell handlers for session history.

class HistoryList(ShellHandler):
    """
    Show overview of all the history.
    """
    is_leaf = True
    handler_type = BuiltinType()

    def __call__(self):
        # Show all entries
        for i, entry in enumerate(self.shell.history):
            print self._color_history_entry(i+1, entry)

    def _color_history_entry(self, index, entry):
        if entry.sandboxing:
            command = '(sandboxed) ' + entry.command
        else:
            command = entry.command

        return (termcolor.colored('%8i ' % index, 'red', attrs=['bold']) +
                termcolor.colored(entry.time_started.strftime('%H:%M:%S'), 'yellow') +
                (termcolor.colored(' success ', 'green', attrs=['bold', 'dark']) if entry.succeeded else
                        termcolor.colored(' failed ', 'red', attrs=['bold'])) +
                termcolor.colored(command, 'green'))


class HistoryShowEntry(ShellHandler):
    """
    Show the tree of executed commands for this history entry.
    """
    handler_type = BuiltinType()
    is_leaf = True

    def __init__(self, entry):
        self.entry = entry

    def __call__(self):
        for r in self.entry.result:
            print TracePrinter(r.trace).print_color()


class HistoryShow(ShellHandler):
    child = HistoryShowEntry
    handler_type = BuiltinType()

    def complete_subhandlers(self, part):
        for i,e in enumerate(self.shell.history):
            if str(i+1).startswith(part):
                yield str(i+1), self.child(e)

    def get_subhandler(self, name):
        try:
            return self.child(self.shell.history[int(name)-1])
        except ValueError: # When 'name' is not an integer
            raise NoSubHandler


class HistoryChildEntry(HistoryShowEntry):
    def __call__(self):
        for r in self.entry.result:
            for io in r.trace.all_io:
                sys.stdout.write(io)
                sys.stdout.flush()
                time.sleep(1)


class HistoryReplay(HistoryShow):
    """
    Replay the output of this command.
    """
    child = HistoryChildEntry


class History(GroupHandler):
    subhandlers = {
            'list': HistoryList,
            'show': HistoryShow,
            'replay': HistoryReplay,
    }
    handler_type = BuiltinType()


class StandaloneShell(Shell):
    """
    The shell that we provide via telnet/http exposes some additional
    commands for session and user management and logging.
    """
    def __init__(self, root_service, pty, logger_interface, history):
        Shell.__init__(self, root_service, pty, logger_interface)
        self.history = history

    @property
    def extensions(self):
        return { 'history': History, }


def start(root_service, interactive=True, cd_path=None, logfile=None):
    """
    Start the deployment shell in standalone modus. (No parrallel execution,
    no server/client. Just one interface, and everything sequential.)
    """
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

    # Initialize service
    root_service = root_service()

    # Loggers
    history_logger = HistoryLogger()
    in_shell_logger = DefaultLogger(print_group=False)
    extra_loggers = root_service.Meta.extra_loggers

    logger_interface = LoggerInterface()
    logger_interface.attach(in_shell_logger)
    logger_interface.attach(history_logger)

    for l in extra_loggers:
        logger_interface.attach(l)

    # Start shell command loop
    print 'Running single threaded shell...'
    shell = StandaloneShell(root_service, pty, logger_interface, history_logger.history)
    if cd_path is not None:
        shell.cd(cd_path)
    shell.cmdloop()

    for l in extra_loggers:
        logger_interface.detach(l)

    logger_interface.detach(in_shell_logger)
    logger_interface.detach(history_logger)
