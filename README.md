Deployer
========

[![Build Status](https://travis-ci.org/jonathanslenders/python-deployer.png)](https://travis-ci.org/jonathanslenders/python-deployer)

The deployer is a Python framework for automatic application deployment on
Posix systems, usually through SSH. When set up, it can be used as a library or
through the interactive command line.

Some key features are:

 - Interactive execution of remote commands, locally, they will appear in a
   pseudo terminal (created with openpty), so that even editors like Vim or
   Emacs works fine when you run them on the remote end.
 - Reusability of all deployment code is a key point. It's as declarative as
   possible, but without loosing Python's power to express everything as
   dynamic as you'd like to. Deployment code is hierarchically structured, with
   inheritance where possible.
 - Parallel execution is easy when enabled, while keeping interaction with
   these remote processes possible through pseudoterminals. Every process gets
   his own terminal, either a new xterm or gnome-terminal window, a tmux pane, or
   whatever you'd like to.
 - Logging of your deployments. New loggers are easily pluggable into the
   system.

Documentation and tutorial
--------------------------

Documentation on readthedocs:

 - [Browse on-line](https://python-deploy-framework.readthedocs.org/en/latest/)
 - [Download PDF](https://media.readthedocs.org/pdf/python-deploy-framework/latest/python-deploy-framework.pdf)


Authors
-------

 - Jonathan Slenders (VikingCo, Mobile Vikings)
 - Jan Fabry (VikingCo, Mobile Vikings)


History
-------

During the summer of 2011, when I was unsatisfied with some of the capabilities
of Fabric, I (Jonathan) started the development of a new, interactive
deployment system from scratch. The first successful deployments (of a Django
project) were done only a few months later, but since then, all the code has
been refactored quite a few times.


