from setuptools import setup, find_packages

setup(
    name="python-deployer",
    version='0.1',
    url='https://github.com/jonathanslenders/python-deployer',
    license='BSD',
    description='Python deployer',
    long_description=open('README.md', 'r').read(),
    author='Jonathan Slenders, Mobile Vikings, City Live nv',
    packages=find_packages('.'),
    classifiers=[
        'Intended Audience :: Developers',
        'Programming Language :: Python',
        'Operating System :: Posix',
    ],
)
