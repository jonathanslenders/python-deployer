Deployer
========

[![Build Status](https://travis-ci.org/jonathanslenders/python-deployer.png)](https://travis-ci.org/jonathanslenders/python-deployer)
[![Build Status](https://drone.io/github.com/jonathanslenders/python-deployer/status.png)](https://drone.io/github.com/jonathanslenders/python-deployer/latest)

Framework for remote execution on Posix systems.

Important key features are:

 - Powerful interactive command line with autocompletion;
 - Interactive and fast parallel execution;
 - Reusability of your code (through inheritance);
 - Normally using SSH for remote execution, but pluggable for other execution methods.

It's more powerful than `Fabric`_, but different from `Saltstack`_. It's not
meant to replace anything, it's another tool for your toolbox.


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
