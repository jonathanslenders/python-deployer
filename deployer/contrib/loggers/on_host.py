from deployer.loggers import Logger, RunCallback, ForkCallback
from deployer.utils import esc1

class OnHostLogger(Logger):
    """
    Log all transactions on every host in:
    ~/.deployer/history
    """
    def __init__(self, username):
        from socket import gethostname
        self.from_host = gethostname()
        self.username = username

    def log_run(self, run_entry):
        if not run_entry.sandboxing:
            run_entry.host._run_silent("""
                mkdir -p ~/.deployer/;
                echo -n `date '+%%Y-%%m-%%d %%H:%%M:%%S | ' ` >> ~/.deployer/history;
                echo -n '%s | %s | %s | ' >> ~/.deployer/history;
                echo '%s' >> ~/.deployer/history;
                """
                % ('sudo' if run_entry.use_sudo else '    ',
                    esc1(self.from_host),
                    esc1(self.username),
                    esc1(run_entry.command or '')
                    ))
        return RunCallback()

    def log_fork(self, fork_entry):
        # Use the same class OnHostLogger in forks.
        class callback(ForkCallback):
            def get_fork_logger(c):
                return OnHostLogger(self.username)
        return callback()
