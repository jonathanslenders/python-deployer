from deployer.console import input
from deployer.contrib.commands import wget
from deployer.contrib.services.apt_get import AptGet
from deployer.contrib.services.config import Config
from deployer.contrib.services.cron import Cron
from deployer.contrib.services.hba import AllowEveryone, DenyEveryone
from deployer.contrib.services.s3 import S3
from deployer.contrib.services.upstart import UpstartService
from deployer.contrib.services.users import User
from deployer.query import Q
from deployer.service import Service, map_roles, required_property, isolate_host
from deployer.utils import esc1

import os


# pg_hba template
pg_hba_template = \
"""
# TYPE  DATABASE        USER            ADDRESS                 METHOD

# "local" is for Unix domain socket connections only
local   all             all                                     trust

# IP v4
host    all             all             127.0.0.1/32            trust

# IP v6
host    all             all             ::1/128                 trust

# For the master, add:
#    host replication all .../32 md5

# For other external hosts, add:
#    host all all %s/32 password
"""

postgres_conf_template = \
"""
# Default configuration
max_connections = 100
shared_buffers = 24MB
datestyle = 'iso,mdy'
lc_messages = 'en_US.UTF-8'
lc_monetary = 'en_US.UTF-8'
lc_numeric = 'en_US.UTF-8'
lc_time = 'en_US.UTF-8'
default_text_search_config = 'pg_catalog.english'
listen_addresses = '*'
log_min_duration_statement = 800 # Log query statements of queries taking longer than 800ms
"""

# Master configuration (appended to postgresql.conf)
postgres_master_conf = postgres_conf_template + \
"""
# Master specific
wal_level = hot_standby
max_wal_senders = 5
hot_standby = off
wal_keep_segments = 5000
"""

# Slave configuration (appended to postgresql.conf)
postgres_slave_conf = postgres_conf_template + \
"""
# Slave specific
hot_standby = on
wal_level = hot_standby
"""

# TODO: maybe add this to postgres.conf if we want to have logging.
postgres_log_conf = \
"""
log_destination = 'csvlog'
logging_collector = 'on'
log_directory = 'pg_log'
log_rotation_age = 1d
log_rotation_size = 10MB
"""


# recovery.conf -> installed on a slave. The slave will sync to the master,
# and be available in read-only (if hot_standby=on). When the trigger_file is
# created. The slave will become read/write and stop syncing.
postgres_recovery_conf = \
"""
standby_mode = 'on'
primary_conninfo = 'host=%(host)s port=5432 user=postgres password=%(password)s'
trigger_file = '/tmp/pgsql.trigger'
"""


# Bash script for taking back-ups.
backup_script = \
"""#!/bin/bash
WEEKDAY=$(date +%%w)
HOUR=$(date +%%H)
tmp_file="postgres-sql-backup-` date +%%Y-%%m-%%d_%%H:%%M:%%S `-ip-` hostname -I | tr -d " " `-%(port)s.sql.gz"
filename="postgres-sql-backup-` date +%%Y/month-%%m/day-%%d/%%H:%%M:%%S `-ip-` hostname -I | tr -d " " `-%(port)s.sql.gz"
/usr/local/pgsql/bin/pg_dumpall --clean | gzip > "/tmp/${tmp_file}"
s3cmd put "/tmp/${tmp_file}" "%(s3_bucket)s/${filename}"
if [ $WEEKDAY == 0 ] && [ $HOUR == 23 ]; then
    env/glacier-cmd/bin/glacier-cmd upload --partsize 64 %(glacier_vault)s /tmp/${tmp_file}
fi
rm "/tmp/${tmp_file}"
"""



class PostgreSQL(Service):
    class Meta(Service.Meta):
        roles = (
                'master', # Master database
                'slaves', # Slave database (optional)
                'allow_hosts',
            )
        # TODO: No isolation right now... master/slave isolation would be very
        # useful!

    #postgresql_download_url = 'http://ftp.postgresql.org/pub/source/v9.1.2/postgresql-9.1.2.tar.gz'
    #geos_download_url = 'http://download.osgeo.org/geos/geos-3.3.1.tar.bz2'
    #postgis_download_url = 'http://postgis.refractions.net/download/postgis-1.5.3.tar.gz'
    #proj_download_url = 'http://download.osgeo.org/proj/proj-4.7.0.tar.gz'

    postgresql_download_url = 'http://ftp.postgresql.org/pub/source/v9.1.4/postgresql-9.1.4.tar.gz'
    proj_download_url = 'http://download.osgeo.org/proj/proj-4.8.0.tar.gz'
    geos_download_url = 'http://download.osgeo.org/geos/geos-3.3.4.tar.bz2'
    postgis_download_url = 'http://postgis.refractions.net/download/postgis-1.5.4.tar.gz'

    # Data directory, slug and port should be unique when you have multiple
    # database instances on a single server.
    postgres_data_directory = '/usr/local/pgsql/data/'
    port = 5432
    slug = required_property()

    s3_bucket = None # e.g. 's3://bucket/directory' # Without trailing slash
    s3_access_key = ''
    s3_secret_key = ''

    # Postgres database password
    password = None

    # Paths

    @property
    def recovery_conf_file(self):
        return os.path.join(self.postgres_data_directory, 'recovery.conf')

    # Hosts

    @property
    def master(self):
        return self.hosts.filter('master')[0]

    @property
    def slaves(self):
        return self.hosts.filter('slaves')

    @map_roles(host=('master', 'slaves'))
    class packages(AptGet):
        # Some general default packages
        packages = (
                'curl',
                'make',
                'gcc',
                'g++',
                'libxml2',
                'libxml2-dev',
                'readline-common',
                'libreadline-dev',
                'libz-dev')

    class _upstart_service(UpstartService):
        """
        Postgres upstart service.
        """
        chdir = '/'
        user = 'postgres'

        @property
        def slug(self):
            return 'postgres-%s' % self.parent.slug

        @property
        def name(self):
            return 'postgres-%s' % self.parent.slug

        def setup(self):
            # Initialize log file
            for host in self.hosts:
                host.sudo('touch /var/log/%s-log' % self.name)
                host.sudo('chown postgres:postgres /var/log/%s-log' % self.name)

            return UpstartService.setup(self) # TODO: self.super does not yet work

        @property
        def command(self):
            return '/usr/local/pgsql/bin/postgres -D "%s" -p "%s" >> /var/log/%s-log 2>&1' % (
                        self.parent.postgres_data_directory, self.parent.port, self.name)

        def monitor_output(self):
            self.hosts.run("tail -f '%s'" % esc1('/var/log/%s-log' % self.name))


    master_upstart_service = map_roles(host='master')(_upstart_service)
    slave_upstart_service = map_roles(host='slaves')(_upstart_service)


    @map_roles(host='master')
    class s3(S3):
        access_key = Q.parent.s3_access_key
        secret_key = Q.parent.s3_secret_key
        username = 'postgres'


    @map_roles(host=('master', 'slaves'))
    class postgres_user(User):
        username = 'postgres'
        home_directory = '/usr/local/pgsql'


    # Actions

    def setup(self):
        """
        Do a bare postgres install.
        Normally you want to call configure_postgres after running this command.
        """
        # Install apt-get packages
        self.packages.install()

        # Install s3cmd for backups
        self.postgres_user.create()

        if self.s3_bucket:
            self.s3.setup()

        # Compile and install postgres
        for host in self.hosts.filter([ 'master', 'slaves' ]):
            host.run(wget(self.postgresql_download_url, 'postgresql.tgz'))
            host.run('tar xvzf postgresql.tgz')

            with host.cd('postgresql-9.1*/'):
                host.run('./configure')
                host.run('make')
                host.sudo('make install')

                # Compile hstore extension as well
                with host.cd('contrib/hstore'):
                    host.run('make')
                    host.sudo('make install')

        print "Don't forget to configure postgres. Probably you want to call 'configure_postgres' now."

    host_based_access = DenyEveryone

    @map_roles(host='slaves')
    class pg_hba_slaves(Config):
        """
        pg_hba.conf files for remote authentication.
        """
        @property
        def remote_path(self):
            return os.path.join(self.parent.postgres_data_directory, 'pg_hba.conf')

        use_sudo = True

        @property
        def content(self):
            return '\n'.join(
                [ pg_hba_template ] +
                [ 'host all all %s password # %s' % t for t in self.parent.host_based_access.allow_tuples ])

        def setup(self):
            Config.setup(self)
            self.hosts.sudo('chown postgres:postgres "%s"' % self.remote_path)

    @map_roles(host='master')
    class pg_hba_master(pg_hba_slaves):
        """
        pg_hba.conf files for remote authentication.
        """
        @property
        def content(self):
            return '\n'.join(
                [ pg_hba_template ] +
                [ 'host all all %s password # %s' % t for t in self.parent.host_based_access.allow_tuples ] +

                # Enable replication access on master
                [ 'host replication all %s/32 md5' % slave.get_ip_address() for slave in self.parent.slaves ])


    @map_roles(host='master')
    class postgres_master_config(Config):
        @property
        def remote_path(self):
            return os.path.join(self.parent.postgres_data_directory, 'postgresql.conf')

        use_sudo = True

        def setup(self):
            self.backup()
            Config.setup(self)
            self.hosts.sudo('chown postgres:postgres "%s"' % self.remote_path)

        content = postgres_master_conf


    @map_roles(host='slaves')
    class postgres_slaves_config(postgres_master_config):
        content = postgres_slave_conf

    def configure_postgres(self):
        """
        Initialize database, and run postgres through upstart.
        You should be able to connect to the database after running this.
        """
        # Make sure we have a postgres user.
        self.postgres_user.create()

        for host in self.hosts.filter([ 'master', 'slaves' ]):
            # Initialize data directory
            if not host.exists(self.postgres_data_directory):
                host.sudo('mkdir -p "%s"' % self.postgres_data_directory)
                host.sudo('chown postgres:postgres "%s"' % self.postgres_data_directory)
                host.sudo('/usr/local/pgsql/bin/initdb -D "%s"' % self.postgres_data_directory, user='postgres')

            # If no PG_VERSION file exists right now, something went wrong.
            if not host.exists(os.path.join(self.postgres_data_directory, 'PG_VERSION')):
                raise Exception('No postgres database initialized in data directory. Call initdb by hand.')

        # Install configs
        self.pg_hba_master.setup()
        self.pg_hba_slaves.setup()
        self.postgres_master_config.setup()
        self.postgres_slaves_config.setup()

        # Install upstart files
        self.master_upstart_service.setup()
        self.master_upstart_service.start()

        self.slave_upstart_service.setup()
        self.slave_upstart_service.start()

        # Set password for postgres user in master database
        self.set_postgres_user_password()

    def set_postgres_user_password(self):
        if self.password:
            self.hosts.filter('master').sudo(r''' echo "ALTER USER postgres WITH PASSWORD '%s';" | /usr/local/pgsql/bin/psql -p %s -U postgres''' %
                                            (self.password, self.port), user='postgres')
        else:
            print 'No password configured.'

    def run_postgres(self, role='master'):
        """
        Run postgres server, but not as background deamon.
        """
        self.hosts.filter(role)[0].run('/usr/local/pgsql/bin/postgres -p %s -D "%s"' %
                        (self.port, self.postgres_data_directory))


    def create_db(self, database):
        """
        Create database in master database.
        """
        self.hosts.filter('master').sudo('/usr/local/pgsql/bin/createdb -p %s -U postgres -E utf8 %s' % (self.port, database), user='postgres')

    def list_db(self):
        """
        List databases
        """
        with self.hosts.filter('master').env('TERM','xterm'):
            #self.hosts['master'].sudo(r''' (echo '\pset columns 10000' && echo '\l') | /usr/local/pgsql/bin/psql -U postgres''')

            self.hosts.filter('master').sudo('/usr/local/pgsql/bin/psql -p %s -U postgres -l' % self.port)
            #self.hosts['master'].start_interactive_shell('/usr/local/pgsql/bin/psql -U postgres -l')

    def shell(self, database='postgres'):
        """
        Open a shell. Prefer the master host if a master is available,
        otherwise, open a shell on a slave.
        """
        if self.hosts.filter('master'):
            host = self.hosts.filter('master')
        else:
            host = self.hosts.filter('slaves')

        host[0].sudo("/usr/local/pgsql/bin/psql -p %s -U postgres -d '%s' " %
                            (self.port, esc1(database)), user='postgres')

    def show_log(self, hostname='master'):
        """
        Show last 50 log entries of today. (This will only output anything if you enabled logging for this server.)
        """
        # TODO: directory is not correct
        self.hosts.filter(hostname).sudo(
            """cat %s/main/pg_log/postgresql-` date +%Y-%m-%d_ `*.csv | tail -n 50 | awk -F "," '{print $1 ": " $14 "," $15}' """ % self.postgres_data_directory)

    def show_pg_stat_activity(self, hostname='master'):
        """
        Show connected hosts (username, ip, ...).
        """
        self.hosts.filter(hostname).sudo('''/usr/local/pgsql/bin/psql -p %s -U postgres -d postgres -c "
                SELECT * from pg_stat_activity; " ''' % self.port)

    def show_pg_stat_replication(self):
        self.hosts.filter('master').sudo('''/usr/local/pgsql/bin/psql -p %s -U postgres -d postgres -c "
                SELECT application_name,state,sync_priority,sync_state FROM pg_stat_replication; " ''' % self.port)

    def show_pg_current_queries(self, database, hostname='master'):
        """
        The function `pg_stat_get_backend_idset' provides a convenient way to
        generate one row for each active server process. For example, to show the
        PIDs and current queries of all server processes:
        """
        self.hosts.filter(hostname).sudo('''/usr/local/pgsql/bin/psql -p %s -U postgres -d %s -c "
                SELECT pg_stat_get_backend_pid(s.backendid) AS procpid,
                       pg_stat_get_backend_activity(s.backendid) AS current_query
                FROM (SELECT pg_stat_get_backend_idset() AS backendid) AS s;" ''' % (self.port, database))

    def show_db_sizes(self):
        query = 'SELECT pg_database.datname,pg_size_pretty(pg_database_size(pg_database.datname)) AS size FROM pg_database;'
        self.hosts.filter('master').sudo('/usr/local/pgsql/bin/psql -p %s -U postgres -d postgres -c "%s"' % (self.port, query))

    def show_table_sizes(self, database='postgres'):
        """
        Show the size of all tables in all relations, ordered by size.
        """
        # http://wiki.postgresql.org/wiki/Disk_Usage
        query = '''
        SELECT nspname || '.' || relname AS "relation",
            pg_size_pretty(pg_relation_size(C.oid)) AS "size"
          FROM pg_class C
          LEFT JOIN pg_namespace N ON (N.oid = C.relnamespace)
          WHERE nspname NOT IN ('pg_catalog', 'information_schema')
          ORDER BY pg_relation_size(C.oid) DESC
          LIMIT 20;
        '''
        self.hosts.filter('master').sudo('/usr/local/pgsql/bin/psql -p %s -U postgres -d "%s" -c "%s"' % (self.port, database, query))

    def show_version(self):
        query = 'SELECT version();'
        self.hosts.filter('master').sudo('/usr/local/pgsql/bin/psql -p %s -U postgres -d postgres -c "%s"' % (self.port, query))

    # ==============[ PostGIS ]============

    def install_postgis(self):
        for host in self.hosts.filter('master', 'slaves'):
            # Install projection library first
            host.run(wget(self.proj_download_url, 'proj.tgz'))
            host.run('tar xvzf proj.tgz')

            with host.cd('proj-4.*/'):
                host.run('./configure')
                host.run('make')
                host.sudo('make install')

            # Install Geos library
            host.run(wget(self.geos_download_url, 'geos.tar.bz2'))
            host.run('tar xvjf geos.tar.bz2')

            with host.cd('geos-3.3.*/'):
                host.run('./configure')
                host.run('make')
                host.sudo('make install')

            # Install postgis library
            host.run(wget(self.postgis_download_url, 'postgis.tgz'))
            host.run('tar xvzf postgis.tgz')

            with host.env('PATH', '/usr/local/pgsql/bin:$PATH', escape=False):
                with host.cd('postgis-1.5*/'):
                    host.run('./configure')
                    host.run('make')
                    host.sudo('make install')

            # For some reason, we are required to run ldconfig on Ubuntu,
            # otherwise, postgres might not find libgeos.so
            host.sudo('ldconfig')

    def configure_postgis(self, database, role='master'):
        # Load postgis symbols into database
        host = self.hosts.filter(role)

        with host.env('PATH', '/usr/local/pgsql/bin:$PATH', escape=False):
            host.run('createlang -p %s -U postgres -d "%s" plpgsql || true' % (self.port, database)) # ||true in order to ignore errors. plpgsql may already be installed
            host.run('psql -p %s -U postgres -d "%s" -f /usr/local/pgsql/share/contrib/postgis-1.5/postgis.sql' % (self.port, database))
            host.run('psql -p %s -U postgres -d "%s" -f /usr/local/pgsql/share/contrib/postgis-1.5/spatial_ref_sys.sql' % (self.port, database))

    # ==============[ Hstore extension ]============

    def configure_hstore(self, database, role='master'):
        # Load postgis symbols into database
        host = self.hosts.filter(role)

        with host.env('PATH', '/usr/local/pgsql/bin:$PATH', escape=False):
            host.run(r''' echo ";CREATE EXTENSION hstore;" | /usr/local/pgsql/bin/psql -U postgres -p %s -d "%s" ''' % (self.port, database))


    # ==============[ Master / Slave ]============

    @map_roles(host='slaves')
    class recovery_conf(Config):
        remote_path = Q.parent.recovery_conf_file
        use_sudo = True

        @property
        def content(self):
            return postgres_recovery_conf % {
                    'host': self.parent.hosts.filter('master')[0].get_ip_address(),
                    'password': self.parent.password,
                }

        def setup(self):
            Config.setup(self)

            # Restart slave
            self.parent.slave_upstart_service.restart()

    def create_master_slave_certificates(self):
        """
        Generate SSH certificate for postgres user on the slave,
        and upload it to the master.

        (We need this, because the master has to be able to rsync his initial postgres
        data directory to the slave, and rsync uses SSH.)
        """
        master = self.master
        self.hosts.filter('master', 'slaves').sudo('chown postgres:postgres /usr/local/pgsql') #TODO: remove

        for slave in self.slaves:
            # Create SSH certificate for user postgres on the slave
            slave.sudo("ssh-keygen -t rsa -f ~postgres/.ssh/postgres -N '' ", user='postgres')

            # Install public certificate on slave
            slave.sudo("cat ~postgres/.ssh/postgres.pub >> ~postgres/.ssh/authorized_keys", user='postgres')

            # Download private certificate
            private_cert = slave.open('/usr/local/pgsql/.ssh/postgres', 'rb', use_sudo=True).read()

            print 'Created certificate'
            print private_cert

            # Install SSH certificate on master
            master.sudo('mkdir -p ~postgres/.ssh/', user='postgres')
            master.sudo('echo "%s" | su postgres -c cat - > ~postgres/.ssh/postgres' % private_cert)
            master.sudo('echo "Host %s\n  IdentityFile ~postgres/.ssh/postgres" >> ~postgres/.ssh/config' % slave.get_ip_address(), user='postgres')


    def sync_slaves_with_master(self):
        """
        Synchronize the slave with the master. This is required before streaming replication will start.
        The data directory of the postgres installation is simply rsync'ed to the slave.
        """
        master = self.master

        if not self.postgres_data_directory[-1] == '/':
            raise Exception('Make sure that your postgres data directory ends with a "/", rsync won\'t work otherwise')

        # Start backup at master
        master.sudo(r''' echo ";SELECT pg_start_backup('backup', true);" | /usr/local/pgsql/bin/psql -p %s''' % self.port, user='postgres')

        for slave in self.slaves:
            # First, make sure that postgres is not running on any slave
            self.slave_upstart_service.stop()

                # TODO: major bug in here: rsync creates a 'postgres'
                # subdirectory inside /mnt/postgres, when this directory does
                # already exist.

            # rsync data to slave server
            master.sudo('rsync -a --delete -v -e ssh %s postgres@%s:%s '
                                    # Don't delete or overwrite any of these
                                    # files.
                                    ' --exclude=postmaster.pid'
                                    ' --exclude=server.crt'
                                    ' --exclude=server.key'
                                    ' --exclude=postgresql.conf'
                                    ' --exclude=pg_hba.conf'
                                    ' --exclude=recovery.conf'
                                    ' --exclude=recovery.done'
                                    ' --exclude=backup_label'
                        % (
                            self.postgres_data_directory,
                            slave.get_ip_address(),
                            self.postgres_data_directory,
                        ), user='postgres')

            # Start postgres again on the slave
            self.slave_upstart_service.start()

        # Stop backup at master
        master.sudo(''' echo ";SELECT pg_stop_backup();" | /usr/local/pgsql/bin/psql -p %s ''' % self.port, user='postgres')

    def execute_sql(self, database, sql, role='master'):
        """
        Run this SQL code.
        (Normally, you only run sql on the master database.)
        """
        self.hosts.filter(role).sudo("echo ';%s;' | /usr/local/pgsql/bin/psql -p '%s' -d '%s' " %
                                        (esc1(sql), esc1(str(self.port)), esc1(database)), user='postgres')

    def streaming_replication_health_indicator(self):
        """
        Health indicator for streaming replication.

        http://www.postgresql.org/docs/9.0/static/warm-standby.html#STANDBY-SERVER-SETUP

        An important health indicator of streaming replication is the amount
        of WAL records generated in the primary, but not yet applied in the
        standby. You can calculate this lag by comparing the current WAL write
        location on the primary with the last WAL location received by the
        standby.
        """
        for h in self.hosts.filter('master'):
            h.sudo(''' echo ";SELECT pg_current_xlog_location();" | /usr/local/pgsql/bin/psql -p %s ''' % self.port, user='postgres')

        for h in self.hosts.filter('slaves'):
            h.sudo(''' echo ";SELECT pg_last_xlog_receive_location();" | /usr/local/pgsql/bin/psql -p %s ''' % self.port, user='postgres')

    def vacuum_analyze(self):
        """
        Gather statistics of the database for internal Postgres/Postgis optimizations.
        (need to be run every now and then.)
        """
        for h in self.hosts.filter('master'):
            h.sudo(''' echo ";VACUUM ANALYZE;" | /usr/local/pgsql/bin/psql -p %s ''' % self.port, user='postgres')

    def reload(self):
        """
        Send HUP signal to database server in order to read the pg_hba and config files again.
        """
        self.hosts.filter('master').sudo("/usr/local/pgsql/bin/pg_ctl --pgdata '%s' reload" % esc1(self.postgres_data_directory), user='postgres')
        self.hosts.filter('slaves').sudo("/usr/local/pgsql/bin/pg_ctl --pgdata '%s' reload" % esc1(self.postgres_data_directory), user='postgres')

    def force_stop(self):
        """
        When the upstart service was stopped, but there are still open connections to the database, it's possible
        it won't stop immediately. You will get following error. This command will tell the database not to wait.

        # psql: FATAL:  the database system is shutting down
        """
        self.hosts.filter('master', 'slaves').sudo("/usr/local/pgsql/bin/pg_ctl --pgdata '%s' -m immediate stop" %
                        esc1(self.postgres_data_directory), user='postgres')

    @map_roles(host='master')
    class backup_cron(Cron):
        """
        Backup cronjob on postgres master
        This backup is created with pg_dumpall, and can be restored as
        # zcat backup-name.sql.gz | psql -U postgres
        """
        # Run every hour
        interval = '23 * * * *'
        username = 'postgres'

        @property
        def slug(self):
            return 'database-backup-%s' % self.parent.port

        @property
        def command(self):
            home = self.hosts[0].get_home_directory('postgres')
            return '%s/backup-database-%s.sh' % (home, self.parent.port)

        def install(self):
            # Create backup script
            for host in self.hosts:
                host.open(self.command, 'wb', use_sudo=True).write(backup_script % {
                            's3_bucket': self.parent.s3_bucket,
                            'glacier_vault': self.parent.glacier_vault,
                            'port': self.parent.port,
                            })

                host.sudo('chown postgres:postgres %s' % self.command)
                host.sudo('chmod +x %s' % self.command)

            # Install cron
            Cron.install(self)

    def restore_backup_from_url(self):
        # ' /usr/local/pgsql/bin/psql -p %s -d template1 -U postgres < backup.sql'
        backup_url = input('Enter the URL of the backup location (an .sql.gz file)')
        for h in self.hosts.filter('master'):
            h.sudo("curl '%s' | gunzip | /usr/local/pgsql/bin/psql -U postgres" % esc1(backup_url),
                                user='postgres')


pg_bouncer_ini_template = \
"""
[databases]
%(db_name)s = host=%(db_address)s port=%(db_port)s dbname=%(db_name)s user=%(db_user)s password=%(db_password)s

[pgbouncer]
default_pool_size = %(default_pool_size)i
pool_mode = session
auth_type = any
listen_port = %(listen_port)s
#listen_addr = 127.0.0.1
unix_socket_dir = %(socket_directory)s
logfile = %(logfile)s
#pidfile = /var/run/pgbouncer-%(slug)s.pid
auth_file = /dev/null
"""

@isolate_host
class PgBouncer(Service):
    # Settings for local installation.

    # Slug, should be unique between all services.
    slug = required_property()

    listen_port = 5432

    # Settings for postgres server
    db_address = '127.0.0.1'
    db_port = 5432
    db_name = 'postgres'
    db_user = 'postgres'
    db_password = ''
    default_pool_size = 40

    username = 'postgres'

    @property
    def logfile(self):
        return '/var/log/pgbouncer-%s.log' % self.slug

    class user(User):
        username = Q.parent.username
        home_directory = '/usr/local/pgsql'


    class packages(AptGet):
        packages = ('pgbouncer',)


    def setup(self):
        self.packages.install()
        self.ini_file.setup()
        self.user.create()
        self.upstart_service.setup()

    def test(self):
        """
        Test connection to database.
        """
        database = input('Enter database name')

        self.hosts.run("psql --host '%s' --port '%s' '%s'" %
                (self.socket_directory, self.listen_port, database))

    def monitor(self):
        """
        Show database connection information, like the hosts and pool_size of pg_bouncer.
        """
        self.hosts.run("psql --host '%s' --port '%s' 'pgbouncer' -c 'show databases;' " %
                (self.socket_directory, self.listen_port))


    @property
    def socket_directory(self):
        return '/var/run/postgresql-%s' % self.slug

    def create_socket_directory(self):
        """
        Make sure that socket directory exists
        """
        self.hosts.sudo("mkdir -p '%s'" % esc1(self.socket_directory))
        self.hosts.sudo("chown -R '%s' '%s'" % (esc1(self.username), esc1(self.socket_directory)))

    @map_roles.just_one
    class ini_file(Config):
        use_sudo = True

        @property
        def remote_path(self):
            return '/etc/pgbouncer-%s.ini' % self.parent.slug

        @property
        def content(self):
            self = self.parent
            return pg_bouncer_ini_template % {
                    'slug': self.slug,
                    'logfile': self.logfile,
                    'listen_port': self.listen_port,
                    'db_address': self.db_address,
                    'db_port': self.db_port,
                    'db_name': self.db_name,
                    'db_user': self.db_user,
                    'db_password': self.db_password,
                    'socket_directory': self.socket_directory,
                    'default_pool_size': self.default_pool_size,
            }

        def setup(self):
            parent = self.parent

            parent.create_socket_directory()

            # Install config
            Config.setup(self)
            self.hosts.sudo("chown '%s' '%s' " % (esc1(parent.username), esc1(self.remote_path)))

            # Give write permissions to logging file
            self.hosts.sudo("touch '%s' " % esc1(parent.logfile))
            self.hosts.sudo("chown '%s' '%s' " % (esc1(parent.username), esc1(parent.logfile)))


    @map_roles.just_one
    class upstart_service(UpstartService):
        """
        pgbouncer upstart service.
        """
        chdir = '/'

        user = Q.parent.username
        slug = property(lambda self: 'pg-bouncer-%s' % self.parent.slug)

        description = 'Start pgbouncer'

        @property
        def command(self):
            return "pgbouncer '%s' " % esc1(self.parent.ini_file.remote_path) # TODO: XXX move [0] behind ini_file.
