from deployer.contrib.services.apt_get import AptGet
from deployer.contrib.services.config import Config
from deployer.contrib.services.cron import Cron
from deployer.query import Q
from deployer.service import Service, required_property, isolate_host
from deployer.utils import esc1

from pygments.lexers import IniLexer


s3_template = \
"""
[default]
access_key = %(access_key)s
acl_public = False
bucket_location = US
cloudfront_host = cloudfront.amazonaws.com
cloudfront_resource = /2008-06-30/distribution
default_mime_type = binary/octet-stream
delete_removed = False
dry_run = False
encoding = UTF-8
encrypt = False
force = False
get_continue = False
gpg_command = /usr/bin/gpg
gpg_decrypt = %%(gpg_command)s -d --verbose --no-use-agent --batch --yes --passphrase-fd %%(passphrase_fd)s -o %%(output_file)s %%(input_file)s
gpg_encrypt = %%(gpg_command)s -c --verbose --no-use-agent --batch --yes --passphrase-fd %%(passphrase_fd)s -o %%(output_file)s %%(input_file)s
gpg_passphrase =
guess_mime_type = True
host_base = s3.amazonaws.com
host_bucket = %%(bucket)s.s3.amazonaws.com
human_readable_sizes = False
list_md5 = False
preserve_attrs = True
progress_meter = True
proxy_host =
proxy_port = 0
recursive = False
recv_chunk = 4096
secret_key = %(secret_key)s
send_chunk = 4096
simpledb_host = sdb.amazonaws.com
skip_existing = False
urlencoding_mode = normal
use_https = True
verbosity = WARNING
"""


@isolate_host
class S3(Service):
    # Amazon S3 authentication
    access_key = required_property()
    secret_key = required_property()

    # The user for which the s3 config is installed
    # (or None for the logged in user)
    username = None

    class packages(AptGet):
        packages = ('s3cmd',)


    class config(Config):
        @property
        def remote_path(self):
            return self.host.sudo('echo -n ~%s/.s3cfg' % (self.parent.username or ''), interactive=False)

        lexer = IniLexer

        # NOTE: we execute this as root, because not every user
        # (e.g. potsgres) has write permission to his own home
        # directory. However, we still make sure that he can
        # read/write to this config file.
        use_sudo = True

        @property
        def content(self):
            return s3_template % {
                    'access_key': self.parent.access_key,
                    'secret_key': self.parent.secret_key,
                }

        def setup(self):
            Config.setup(self)

            if self.parent.username:
                self.host.sudo('chown %s ~%s/.s3cfg' % (self.parent.username, self.parent.username))


    def setup(self):
        """
        Install s3 configuration
        """
        # Install s3cmd
        self.packages.install()

        # Install config
        self.config.setup()



class S3_DirectoryBackup(Service):
    slug = required_property()
    username = required_property()

    access_key = required_property()
    secret_key = required_property()

    local_directory = required_property()
    s3_bucket = required_property() # e.g. s3://my-bucket/my-directory/ (should end with a slash)

    follow_symlinks = False

    class s3(S3):
        access_key = Q.parent.access_key
        secret_key = Q.parent.secret_key
        username = Q.parent.username

    class cron(Cron):
        # Run every hour
        interval = '8 * * * *'
        username = Q.parent.username
        slug = Q.parent.slug

        @property
        def command(self):
            return "s3cmd put -r %s '%s' '%s'" % (
                    ('--follow-symlinks' if self.parent.follow_symlinks else ''),
                    esc1(self.parent.local_directory),
                    esc1(self.parent.s3_bucket))


    def setup(self):
        self.s3.setup()
        self.cron.install()
