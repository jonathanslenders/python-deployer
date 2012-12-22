#!/usr/bin/env python
from setuptools import setup, find_packages

setup(
    name="python-deployer",
    version='0.1',
    url='https://github.com/jonathanslenders/python-deployer',
    license='LICENSE.txt',
    description='Python deployer',
    long_description=open('README.md', 'r').read(),
    author='Jonathan Slenders, Mobile Vikings, City Live nv',
    author_email='jonathan.slenders@mobilevikings.com',
    packages=find_packages('.'),
    install_requires = [
        'paramiko==1.9.0',
        'Twisted==12.2.0',
        'pexpect==2.4',
        'Pygments==1.5',
        'termcolor==1.1.0',
        ],
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: System Administrators'
        'Operating System :: POSIX',
        'Programming Language :: Python',
        'Topic :: System :: Installation/Setup',
        'Topic :: System :: Shells',
    ],
)
