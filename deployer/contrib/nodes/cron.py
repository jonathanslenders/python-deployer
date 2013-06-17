from deployer.node import SimpleNode, required_property


class cron_intervals:
    every_15_minutes = '0/15 * * * *'
    every_hour = '0 * * * *'
    every_20_minutes = '0/20 * * * *'
    every_minute = '* * * * *'
    every_day = '1 4 * * *'


class Cron(SimpleNode):
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

    def activate_all(self):
        home = self.host.get_home_directory(self.username)
        self.host.sudo('cat %s/.deployer-crons/* | crontab' % home, user=self.username)

    # Deprecated (confusing naming)
    def install(self):
        self.add(skip_activate=False)

    def add(self, skip_activate=False):
        """
        Install cronjob
        (This will leave the other cronjobs, created by this service intact.)
        """
        # Get home directory for this user
        home = self.host.get_home_directory(self.username)

        # Create a subdirectory .deployer-crons if this does not yet exist
        self.host.sudo('mkdir -p %s/.deployer-crons' % home)
        self.host.sudo('chown %s %s/.deployer-crons' % (self.username, home))

        # Write this cronjob into deployer-crons/slug
        self.host.open('%s/.deployer-crons/%s' % (home, self.slug), 'wb', use_sudo=True).write(self.cron_line)
        self.host.sudo('chown %s %s/.deployer-crons/%s' % (self.username, home, self.slug))

        if not skip_activate:
            self.activate_all()

    # Deprecated (confusing naming)
    def uninstall(self):
        self.remove(skip_activate=False)

    def remove(self, skip_activate=False):
        """
        Uninstall cronjob
        """
        # Get home directory for this user
        home = self.host.get_home_directory(self.username)

        # Remove this cronjob
        path = '%s/.deployer-crons/%s' % (home, self.slug)
        if self.host.exists(path):
            self.host.sudo("rm '%s' " % path)

        if not skip_activate:
            self.activate_all()

    @property
    def cron_line(self):
        cron_line = '%s %s\n' % (self.interval, self.command)
        if self.doc:
            cron_line = "\n".join(["# %s" % l for l in self.doc.split('\n')] + [cron_line])
        return cron_line

    def show_new_line(self):
        print self.cron_line

    def run_now(self):
        self.host.sudo(self.command, user=self.username)

    def list_all_crons(self):
        # Get home directory for this user
        home = self.host.get_home_directory(self.username)

        # Print crontabs
        self.host.sudo('cat %s/.deployer-crons/* ' % home, user=self.username)
