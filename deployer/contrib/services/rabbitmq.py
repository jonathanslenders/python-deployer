from deployer.contrib.services.apt_get import AptGet
from deployer.contrib.services.sysvinit import SysVInitService
from deployer.exceptions import ExecCommandFailed
from deployer.service import Service
from deployer.utils import esc1


class RabbitMQ(Service):
    vhosts = {}
    users = {'guest': False}
    plugins = ('rabbitmq_management',)
    mnesia_base = ''

    class packages(AptGet):
        packages = ('rabbitmq-server', 'erlang-inets')
        extra_sources = {'rabbitmq': ['deb http://www.rabbitmq.com/debian/ testing main']}
        extra_key_urls = ('http://www.rabbitmq.com/rabbitmq-signing-key-public.asc',)

    class init_service(SysVInitService):
        slug = 'rabbitmq-server'
        no_pty = True

    def setup(self):
        self.packages.setup_extra()
        self.packages.install()

        self.setup_config()

        self.init_service.restart()
        self.enable_plugins()

        for vhost in self.vhosts:
            self.add_vhost(vhost)

        for user, info in self.users.items():
            if not info:
                self.delete_user(user)
            else:
                password = admin = vhosts = False
                if isinstance(info, basestring):
                    password = info
                else:
                    password = info[0]
                    admin = info[1]
                    vhosts = info[2:]
                self.add_user(user, password, admin)
                if vhosts:
                    for vhost in vhosts:
                        self.add_user_to_vhost(user, vhost)

    def setup_config(self):
        if self.mnesia_base:
            self.hosts.sudo("mkdir -p '%s'" % esc1(self.mnesia_base))
            self.hosts.sudo("chown rabbitmq:rabbitmq '%s'" % esc1(self.mnesia_base))
            self.hosts.sudo("echo export RABBITMQ_MNESIA_BASE='%s' >> /etc/default/rabbitmq-server" % esc1(self.mnesia_base))


    def enable_plugins(self):
        for plugin in self.plugins:
            self.enable_plugin(plugin)

    def enable_plugin(self, plugin):
        self.hosts.sudo("rabbitmq-plugins enable '%s'" % esc1(plugin))
        self.init_service.restart()


    def add_user(self, user, password, admin=True):
        try:
            self.hosts.sudo("rabbitmqctl list_users | grep '%s'" % user)
        except ExecCommandFailed:
            self.hosts.sudo("rabbitmqctl add_user '%s' '%s'" % (esc1(user), esc1(password)))
        if admin:
            self.hosts.sudo("rabbitmqctl set_user_tags '%s' administrator" % esc1(user))

    def add_vhost(self, vhost, user=None):
        try:
            self.hosts.sudo("rabbitmqctl list_vhosts | grep '%s'" % vhost)
        except ExecCommandFailed:
            self.hosts.sudo("rabbitmqctl add_vhost '%s'" % esc1(vhost))
        if user:
            self.add_user_to_vhost(vhost, user)

    def add_user_to_vhost(self, vhost, user):
        self.hosts.sudo("rabbitmqctl set_permissions -p '%s' '%s' '.*' '.*' '.*'" % (esc1(vhost), esc1(user)))

    def delete_user(self, user):
        try:
            self.hosts.sudo("rabbitmqctl list_users | grep '%s'" % user)
        except ExecCommandFailed:
            return True
        self.hosts.sudo("rabbitmqctl delete_user '%s'" % esc1(user))
