from deployer.service import Service, isolate_host, required_property


class cron_intervals:
    every_15_minutes = '0/15 * * * *'
    every_hour = '0 * * * *'
    every_20_minutes = '0/20 * * * *'
    every_minute = '* * * * *'
    every_day = '1 4 * * *'


@isolate_host
class Cron(Service):
    # ===============[ Cron config ]================

    interval = '20 * * * *' # Every hour by default

    # Username of the user as which the cron should be executed.  e.g.: 'username'
    username = required_property()

    # The command that this cron has to execute.  e.g.: 'echo "dummy command"'
    command = required_property()

    # Should be unique between all crons.
    slug = required_property()

    @property
    def doc(self):
        return self.slug

    # ===============[ Tasks ]================

    def activate_all(self, host=None):
        hosts = [host] if host else self.hosts
        for host in hosts:
            home = host.get_home_directory(self.username)
            host.sudo('cat %s/.deployer-crons/* | crontab' % home, user=self.username)

    # Deprecated (confusing naming)
    def install(self):
        self.add(skip_activate=False)

    def add(self, skip_activate=False):
        """
        Install cronjob
        (This will leave the other cronjobs, created by this service intact.)
        """
        for host in self.hosts:
            # Get home directory for this user
            home = host.get_home_directory(self.username)

            # Create a subdirectory .deployer-crons if this does not yet exist
            host.sudo('mkdir -p %s/.deployer-crons' % home)
            host.sudo('chown %s %s/.deployer-crons' % (self.username, home))

            # Write this cronjob into deployer-crons/slug
            host.open('%s/.deployer-crons/%s' % (home, self.slug), 'wb', use_sudo=True).write(self.cron_line)
            host.sudo('chown %s %s/.deployer-crons/%s' % (self.username, home, self.slug))

            if not skip_activate:
                self.activate_all(host)

    # Deprecated (confusing naming)
    def uninstall(self):
        self.remove(skip_activate=False)

    def remove(self, skip_activate=False):
        """
        Uninstall cronjob
        """
        for host in self.hosts:
            # Get home directory for this user
            home = host.get_home_directory(self.username)

            # Remove this cronjob
            path = '%s/.deployer-crons/%s' % (home, self.slug)
            if host.exists(path):
                host.sudo("rm '%s' " % path)

            if not skip_activate:
                self.activate_all(host)

    @property
    def cron_line(self):
        cron_line = '%s %s\n' % (self.interval, self.command)
        if self.doc:
            cron_line = "\n".join(["# %s" % l for l in self.doc.split('\n')] + [cron_line])
        return cron_line

    def show_new_line(self):
        print self.cron_line

    def run_now(self):
        self.hosts.sudo(self.command, user=self.username)

    def list_all_crons(self):
        for host in self.hosts:
            # Get home directory for this user
            home = host.get_home_directory(self.username)

            # Print crontabs
            host.sudo('cat %s/.deployer-crons/* ' % home, user=self.username)
