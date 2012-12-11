from deployer.console import input
from deployer.contrib.services.apt_get import AptGet
from deployer.contrib.services.config import Config
from deployer.exceptions import ExecCommandFailed
from deployer.service import Service, isolate_host, supress_action_result, map_roles, dont_isolate_yet
from deployer.query import Q
from deployer.utils import esc1

import os
import posixpath


def _pip_install(suffix=''):
    return "pip install --exists-action=w %s" % suffix

@isolate_host
class VirtualEnv(Service):
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

    # This can be python2.6 too, or None if you want to use the default for the system
    python_version = 'python2.7'

    def setup(self):
        """
        Setup virtualenv
        """
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
            python_req = '-p %s' % esc1(self.python_version) if self.python_version else ''
            self.host.run(". /usr/local/bin/virtualenvwrapper.sh && mkvirtualenv '%s' %s || true" % (esc1(self.virtual_env_location), python_req))

            # The or-true at the end is not really the way to go, but
            # somehow, when we run mkvirtualenv this way, it return status
            # code 1, and it will not create the the following user
            # scripts into the virtual env, however the virtual env works
            # perfectly fine.
            # ** predeactivate, postdeactivate, preactivate, postactivate, get_env_details

    @map_roles.just_one
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
        with self.hosts.prefix(self.activate_cmd):
            for f in self.requirements_files:
                self.hosts.run(_pip_install("-r '%s'" % esc1(f)))

            for r in self.requirements:
                self.hosts.run(_pip_install("'%s'" % esc1(r)))

    def upgrade_requirements(self):
        """
        Upgrade packages through PIP.
        """
        with self.hosts.prefix(self.activate_cmd):
            for f in self.requirements_files:
                self.hosts.run(_pip_install("-U -r '%s'" % esc1(f)))

            for r in self.requirements:
                self.hosts.run(_pip_install("-U '%s'" % esc1(r)))

    def upgrade_requirements_since(self, commit='-1', end_commit=None):
        """
        Upgrade requirements changed since a commit.

        If you pass a negative number as the commit SHA, it means "the Nth change of the file".
        So -1 means the last change, -2 the change before that, ...
        """
        requested_end_commit = end_commit
        for host in self.hosts:
            with host.prefix(self.activate_cmd):
                for requirements_file in self.requirements_files:
                    # Change to directory, otherwise we need --git-dir,
                    # which doesn't work with specifing files (git log -- <file>)
                    with host.cd(posixpath.dirname(requirements_file)):
                        # Define start and end commits
                        start_commit = commit
                        if commit[0] == '-':
                            log_count = int(commit) - 1 # We want the changes before this one
                            start_commit = host.run("git  log --pretty=%%h %s -- '%s' | tail -1" % (log_count, esc1(requirements_file)), interactive=False).strip()

                        # Or should end_commit always be HEAD?
                        # Now we might miss changes in the file that are not committed
                        # (Of course, they should be missed - don't forget to commit your stuff, dammit!)
                        end_commit = requested_end_commit
                        if not end_commit:
                            end_commit = host.run("git log --pretty=%h -1 | tail -1", interactive=False).strip()

                        # Take diff of the requirements file
                        requirements_diff = host.run("git diff %s..%s -- '%s'" % (start_commit, end_commit, esc1(requirements_file)), interactive=False)
                        DIFF_HEADER_LINE_COUNT = 5
                        requirements_to_update = []
                        if 0 < len(requirements_diff):
                            for line in requirements_diff.splitlines()[DIFF_HEADER_LINE_COUNT:]:
                                if '+' == line[0]:
                                    requirements_to_update.append(line[1:])

                        # Also update lines with 'auto-update'
                        try:
                            requirements_autoupdate = host.run("grep auto-update '%s'" % esc1(requirements_file), interactive=False)
                            for r in requirements_autoupdate.splitlines():
                                if r not in requirements_to_update:
                                    requirements_to_update.append(r)
                        except ExecCommandFailed:
                            # Nothing found in grep, no problem
                            pass

                        if 0 == len(requirements_to_update):
                            print 'No requirements to update'
                            continue

                        # Write lines to a file, pass it to pip
                        requirements_diff_file = '/tmp/requirements-%s-%s.txt' % (start_commit, end_commit)
                        host.open(requirements_diff_file, 'w').write('\n'.join(requirements_to_update))
                        host.run(_pip_install("--no-dependencies -U -r '%s'" % esc1(requirements_diff_file)))
                        host.run("rm '%s'" % esc1(requirements_diff_file))

    @dont_isolate_yet
    def install_package(self, package=None):
        if not package:
            package = input('Enter package')
        self._install_package(package)

    def _install_package(self, package):
        """
        Install package manually through PIP.
        """
        with self.hosts.prefix(self.activate_cmd):
            self.hosts.run(_pip_install("-U '%s'" % esc1(package)))

    def install_ipython(self, version='0.10.2'):
        self.install_package('ipython==%s' % version)

    @supress_action_result
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

    @map_roles.just_one
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

    # Some extensions

    def all_git_versions(self):
        """
        Print GIT versions for all packages in ~/env/name/src/*
        Returns space-separated tuples (package, commit, tag)
        """
        h  = self.host

        with h.cd(self.virtual_env_location):
            with h.cd('src'):
                h.run('for l in `ls`; do '
                        '(test -d $l && cd $l; test -d .git && '
                                        'echo -n "$l " && '
                                        'echo -n "` git rev-parse HEAD ` " && '
                                        'git describe --tags 2>/dev/null'
                         ');'
                    ' done')


    def fix_distribute(self):
        """
        If you get the following import error during any install
        in the virtualenv, this will fix it.

        >> from pkg_resources import load_entry_point
        ImportError: No module named pkg_resources

        http://stackoverflow.com/questions/7446187/no-module-named-pkg-resources
        """
        with self.host.prefix(self.activate_cmd):
            self.host.run('curl http://python-distribute.org/distribute_setup.py | python')
