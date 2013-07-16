from deployer.contrib.nodes.apt_get import AptGet
from deployer.contrib.nodes.config import Config
from deployer.exceptions import ExecCommandFailed
from deployer.node import SimpleNode, suppress_action_result, dont_isolate_yet
from deployer.query import Q
from deployer.utils import esc1

import os


def _pip_install(suffix='', use_mirrors=True):
    use_mirrors = '--use-mirrors' if use_mirrors else ''
    return "pip install %s --exists-action=w %s" % (use_mirrors, suffix)

class VirtualEnv(SimpleNode):
    """
    VirtualEnv/Python/Pip installation
    """
    # List of requirement files
    requirements_files = ()

    # List of additional requirements
    requirements = ()

    # Location where the virtual env is installed
    virtual_env_location = None

    # Paths to be added using add2virtualenv
    path_extensions = ()

    # This can be python2.6 or python2.7 if you don't want to use the system default
    python_version = 'python'

    def setup(self, force_upgrade=False):
        """
        Setup virtualenv
        """
        if force_upgrade or not self.host.exists('/usr/local/bin/virtualenvwrapper.sh'):
            # Install packages
            self.packages.install()

            self.host.sudo('easy_install pip')
            self.host.sudo('pip install -U pip virtualenv virtualenvwrapper')

        # Install requirements
        self.mkvirtualenv()
        self.install_requirements()

        # Add path extensions
        self.path_extensions_file.setup()

    @property
    def activate_cmd(self):
        return ". %s/bin/activate" % self.virtual_env_location

    @property
    def python_cmd(self):
        return "%s/bin/python" % self.virtual_env_location

    def mkvirtualenv(self):
        with self.host.env('WORKON_HOME', os.path.dirname(self.virtual_env_location)):
            # Find python executable.
            python = self.host.run('which %s' % (self.python_version or 'python')).strip()

            with self.host.env('VIRTUALENVWRAPPER_PYTHON', python):
                self.host.run(". /usr/local/bin/virtualenvwrapper.sh && mkvirtualenv '%s' || true" % esc1(self.virtual_env_location))

                # The or-true at the end is not really the way to go, but
                # somehow, when we run mkvirtualenv this way, it return status
                # code 1, and it will not create the the following user
                # scripts into the virtual env, however the virtual env works
                # perfectly fine.
                # ** predeactivate, postdeactivate, preactivate, postactivate, get_env_details

    class packages(AptGet):
        @property
        def packages(self):
            return ('python-setuptools', 'python-dev', 'build-essential',
                        'git-core', 'mercurial')

        @property
        def packages_if_available(self):
            # Install also python2.7 when it's required for the virtualenv.
            if self.parent.python_version == 'python2.7':
                return ('python2.7', 'git')
            else:
                return ('python', 'git')

    # Pip

    def install_requirements(self):
        """
        Install packages through PIP.
        """
        with self.host.prefix(self.activate_cmd):
            for f in self.requirements_files:
                self.host.run(_pip_install("-r '%s'" % esc1(f)))

            for r in self.requirements:
                self.host.run(_pip_install("'%s'" % esc1(r)))

    def upgrade_requirements(self):
        """
        Upgrade packages through PIP.
        """
        with self.host.prefix(self.activate_cmd):
            for f in self.requirements_files:
                self.host.run(_pip_install("-U -r '%s'" % esc1(f)))

            for r in self.requirements:
                self.host.run(_pip_install("-U '%s'" % esc1(r)))

    @dont_isolate_yet
    def install_package(self, package=None):
        if not package:
            package = self.console.input('Enter package')
        self._install_package(package)

    def _install_package(self, package):
        """
        Install package manually through PIP.
        """
        with self.host.prefix(self.activate_cmd):
            self.host.run(_pip_install("-U '%s'" % esc1(package)))

    def install_ipython(self, version='0.10.2'):
        self.install_package('ipython==%s' % version)

    @suppress_action_result
    def freeze(self):
        """
        pip freeze
        """
        with self.host.prefix(self.activate_cmd):
            return self.host.run("pip freeze")

    def find_version_of_package(self, package):
        """
        Return the installed version of a certain package
        """
        with self.host.prefix(self.activate_cmd):
            try:
                return self.host.run("pip freeze | grep '^%s' " % esc1(package)).strip()
            except ExecCommandFailed:
                # Nothing found in grep, return None
                return None

    # Site-packages location
    @property
    def site_packages_location(self):
        return self.host.run('%s/bin/python -c "from distutils.sysconfig import get_python_lib; print get_python_lib()" ' %
                    self.virtual_env_location, interactive=False).strip()

    # Path extensions
    @property
    def path_extensions_location(self):
        return os.path.join(self.site_packages_location, '_deployer_path_extensions.pth')

    class path_extensions_file(Config):
        remote_path = Q.parent.path_extensions_location

        @property
        def content(self):
            h = self.host

            # We only add new extensions, so the content of this file contains
            # the current, installed extensions + the one that we define.
            if h.exists(self.remote_path):
                extensions = [ e.strip() for e in h.open(self.remote_path, 'r').read().split('\n') ]
            else:
                extensions = []

            for e in self.parent.path_extensions:
                if e not in extensions:
                    extensions.append(e)

            return ''.join('%s\n' % e for e in extensions)
