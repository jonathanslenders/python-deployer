import sys
import datetime

from contextlib import nested

__all__ = ('Actions', 'LoggerInterface', 'CliActionCallback', 'RunCallback', 'FileCallback', 'Logger', 'DummyLoggerInterface')


#
# Interface: group of loggers which can attach multiple loggers.
#


class Actions(object):
    Run = 'run'
    Open = 'open'
    Put = 'put'
    Get = 'get'
    Fork = 'fork'


class LoggerInterface(object):
    """
    Base class for logging interaction on hosts.
    (Not threadsafe)
    """
    def __init__(self):
        self.loggers = []

    def attach(self, logger):
        """
        Attach logger to logging interface.
        """
        self.loggers.append(logger)
        logger.attach()

    def detach(self, logger):
        """
        Remove logger from logging interface.
        """
        self.loggers.remove(logger)
        logger.detach()

    def attach_in_block(self, logger):
        class LoggerAttachment(object):
            def __enter__(context):
                self.attach(logger)

            def __exit__(context, *a):
                self.detach(logger)
        return LoggerAttachment()

    def group(self, func_name, *args, **kwargs):
        class LogGroup(object):
            def __enter__(context):
                context.loggers = self.loggers[:]
                for l in context.loggers:
                    l.enter_group(func_name, *args, **kwargs)

            def __exit__(context, *a):
                for l in context.loggers:
                    l.leave_group()

        return LogGroup()

    def log_cli_action(self, command, sandboxing):
        class CliAction(object):
            def __init__(entry, command, sandboxing):
                entry.time_started = datetime.datetime.now()
                entry.time_ended = None
                entry.command = command
                entry.sandboxing = sandboxing

                entry.result = None
                entry.succeeded = None
                entry.exception = None
                entry.traceback = None

                entry._callbacks = [ l.log_cli_action(entry) for l in self.loggers ]

            def set_failed(entry, exception, traceback):
                entry.time_ended = datetime.datetime.now()
                entry.exception = exception
                entry.traceback = traceback
                entry.succeeded = False

                for c in entry._callbacks:
                    c.completed()

            def set_succeeded(entry, result):
                entry.time_ended = datetime.datetime.now()
                entry.result = result
                entry.succeeded = True

                for c in entry._callbacks:
                    c.completed()

        return CliAction(command, sandboxing)

    def log_fork(self, fork_name):
        class Fork(object):
            entry_type = Actions.Fork

            def __init__(entry):
                entry.fork_name = fork_name
                entry._callbacks = [ l.log_fork(entry) for l in self.loggers ]
                entry.succeeded = None
                entry.exception = None

            def set_succeeded(entry):
                entry.succeeded = True
                for c in entry._callbacks:
                    c.completed()

            def set_failed(entry, exception):
                entry.succeeded = False
                entry.exception = exception

                for c in entry._callbacks:
                    c.completed()

            def get_logger_interface(entry):
                """
                Return a new logger interface object, which will be used
                in this fork (thread).
                """
                interface = LoggerInterface()
                for c in entry._callbacks:
                    interface.attach(c.get_fork_logger())
                return interface
        return Fork()

    def log_run(self, *a, **kwargs):
        """
        Log SSH commands.
        """
        class Run(object):
            entry_type = Actions.Run

            def __init__(entry, host=None, command=None, use_sudo=False, sandboxing=False, interactive=False, shell=False):
                entry.host = host
                entry.command = command
                entry.use_sudo = use_sudo
                entry.sandboxing = sandboxing
                entry.interactive = interactive
                entry.shell = shell
                entry.status_code = 'unknown'

                entry._callbacks = []
                entry._io = []

            def log_io(entry, data):
                """ Log received I/O """
                entry._io.append(data)
                for c in entry._callbacks:
                    c.log_io(data)

            def set_status_code(entry, status_code):
                entry.status_code = status_code

            @property
            def succeeded(entry):
                return entry.status_code == 0

            @property
            def io(entry):
                return ''.join(entry._io)

            def __enter__(entry):
                entry._callbacks = [ l.log_run(entry) for l in self.loggers ]
                return entry

            def __exit__(entry, *a):
                for c in entry._callbacks:
                    c.completed()

        return Run(*a, **kwargs)


    def log_file(self, host, action, **kwargs):
        """
        Log a get/put/open actions on remote files.
        """
        class File(object):
            entry_type = action # e.g. Actions.Get

            def __init__(entry, host, mode=None, remote_path=None, local_path=None, use_sudo=False, sandboxing=False):
                entry.host = host
                entry.remote_path = remote_path
                entry.local_path = local_path
                entry.mode = mode # Required for 'open()' action.
                entry.use_sudo = use_sudo
                entry.sandboxing = sandboxing
                entry.succeeded = None # Unknown yet

            def complete(entry, succeeded=True):
                entry.succeeded = succeeded

            def __enter__(entry):
                entry._callbacks = [ l.log_file_opened(entry) for l in self.loggers ]
                return entry

            def __exit__(entry, *a):
                for c in entry._callbacks:
                    c.file_closed()

        return File(host, **kwargs)


class DummyLoggerInterface(LoggerInterface):
    """
    Dummy logger, does nothing
    """
    pass



#
# Base logger
#

class Logger(object):
    # Keep track of how many times the logger has been attached.

    @property
    def attach_count(self):
        return getattr(self, '_attach_count', 0)

    @attach_count.setter
    def attach_count(self, value):
        self._attach_count = value

    def attach(self):
        if self.attach_count == 0:
            self.attached_first()

        self.attach_count += 1

    def detach(self):
        self.attach_count -= 1

        if self.attach_count == 0:
            self.detached_last()

    #
    # Following methods are to be overriden by specific loggers.
    #

    def attached_first(self):
        pass

    def detached_last(self):
        pass

    def enter_group(self, func_name, *args, **kwargs):
        pass

    def leave_group(self):
        pass

    def log_cli_action(self, action_entry):
        return CliActionCallback()

    def log_fork(self, fork_name):
        return ForkCallback()

    def log_run(self, run_entry):
        return RunCallback()

    def log_file_opened(self, file_entry):
        return FileCallback()


#
# Callbacks
#

class CliActionCallback(object):
    def __init__(self, completed=None):
        if completed:
            self.completed = completed

    def completed(self):
        pass


class RunCallback(object):
    def __init__(self, completed=None, log_io=None):
        if completed:
            self.completed = completed

        if log_io:
            self.log_io = log_io

    def completed(self):
        pass

    def log_io(self, data):
        pass


class FileCallback(object):
    def __init__(self, file_closed=None):
        if file_closed:
            self.file_closed = file_closed

    def file_closed(self):
        pass

class ForkCallback(object):
    def completed(self):
        pass

    def get_fork_logger(self):
        # Return Dummy logger
        return Logger()
