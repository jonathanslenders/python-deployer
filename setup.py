#!/usr/bin/env python
from setuptools import setup, find_packages


LONG_DESCRIPTION = """\
The deployer is a Python framework for automatic application deployment on
Posix systems, usually through SSH. When set up, it can be called as a
library, but usually, people use it through an interactive command line.

Some key features are:

* Interactive execution of remote commands, locally, they will appear in a
  pseudo terminal (created with openpty), so that even editors like Vim or
  Emacs works fine when you run them on the remote end.
* Reusability of all deployment code is a key point. It's as declarative as
  possible, but without loosing Python's power to express everything as
  dynamic as you'd like to. Deployment code is hierarchically structured, with
  inheritance where possible.
* Parallel execution is easy when enabled, while keeping interaction with
  these remote processes possible through pseudoterminals. Every process gets
  his own terminal, either a new xterm or gnome-terminal window, a tmux pane, or
  whatever you'd like to.
* Logging of your deployments. New loggers are easily pluggable into the
  system.
"""

import deployer

setup(
    name="deployer",
    version=deployer.__version__,
    url='https://github.com/jonathanslenders/python-deployer',
    license='LICENSE.txt',
    description='Library for automating system deployments',
    long_description=LONG_DESCRIPTION,
    author='Jonathan Slenders, Mobile Vikings, City Live nv',
    author_email='jonathan.slenders@mobilevikings.com',
    packages=find_packages('.'),
    install_requires = [
        'paramiko>=1.12.0',
        'Twisted>=12.2.0',
        'pexpect==3.0',
        'Pygments>=1.5',
        'termcolor>=1.1.0',
        'docopt==0.6.1',
        'setproctitle==1.1.8',
        ],
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: System Administrators',
        'Operating System :: POSIX',
        'Programming Language :: Python',
        'Topic :: System :: Installation/Setup',
        'Topic :: System :: Shells',
    ],
)
