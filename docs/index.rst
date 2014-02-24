.. python-deploy-framework documentation master file, created by
   sphinx-quickstart on Thu Jun 20 22:12:13 2013.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Python-deploy-framework
=======================

Framework for remote execution on Posix systems.

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

Important key features are:

 - Powerful interactive command line with autocompletion;
 - Interactive and fast parallel execution;
 - Reusability of your code (through inheritance);
 - Normally using SSH for remote execution, but pluggable for other execution methods;
 - Pluggable logging framework;
 - All scripts can be used as a library, easy to call from another Python application. (No global state.)

It's more powerful than `Fabric`_, but different from `Saltstack`_. It's not
meant to replace anything, it's another tool for your toolbox.

.. _Fabric: http://docs.fabfile.org/
.. _Saltstack: http://saltstack.com

Questions? Just `create a ticket <create-ticket>`_ in Github for now:

.. _create-ticket: https://github.com/jonathanslenders/python-deployer/issues?state=open

 - :ref:`Read the tutorial <getting-started>`
 - Find the source code at `github`_.

.. _github: https://github.com/jonathanslenders/python-deployer

.. _table-of-contents:

Table of contents
-----------------

.. toctree::
   :maxdepth: 3

   pages/getting_started
   examples/django-deployment
   pages/architecture_of_roles_and_nodes
   pages/interactive_shell

   pages/node
   pages/node_reference
   pages/host
   pages/host_container
   pages/groups
   pages/console
   pages/inspection
   pages/query
   pages/utils
   pages/exceptions
   pages/pseudo_terminal
   pages/internals

   pages/about
