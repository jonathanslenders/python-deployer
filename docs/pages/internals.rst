.. _internals:

Internals
=========

This page will try to give a high level overview of how the framework is
working. While the end-user of the framework won't usually touch much more than
the ``Node`` and ``Host`` classes, there's a lot more going on underneat.

There's a lot of meta-programming, some domain specific languages, and a
mix of event-driven and blocking code.


Data flow
----------

Roughly, this is the current flow from the interactive shell untill the actual
SSH client.

.. graphviz::

   digraph internals{
       "Node" [style=filled, fillcolor=gold1];
       "ParallelNode" [style=filled, fillcolor=gold1];
       "Host" [style=filled, fillcolor=gold1];

       "Host" [shape=box];
       "HostContainer" [shape=box];
       "HostsContainer" [shape=box];
       "Node" [shape=box];
       "ParallelNode" [shape=box];
       "Env" [shape=box];
       "HostContext" [shape=box];

       "Host" -> "HostContext";
       "Host" -> "Paramiko (SSH)";
       "HostsContainer" -> "Host";
       "HostContainer" -> "Host";
       "HostsContainer" -> "HostContext";
       "HostContainer" -> "HostContext";
       "Node" -> "HostsContainer";
       "ParallelNode" -> "HostsContainer";
       "ParallelNode" -> "HostContainer";
       "Env" -> "Node";
       "Env" -> "ParallelNode";
       "Interactive shell" -> "Env";
   }

   

The yellow classes -- :class:`Node <deployer.node.base.Node>`,
:class:`ParallelNode <deployer.node.base.ParallelNode>` and :class:`Host
<deployer.host.Host>` -- are the ones which an average end-user of this
framework will use. He will inherit from there to define his deployment script.

:class:`HostContainer <deployer.host_container.HostContainer>` (singular and
plural) and :class:`Env <deployer.node.base.Env>` are proxy classes. They are
created by the framework, but passed to the user's code at some points.

``Paramiko``, at the lowest level, is responsible for the SSH connection. The
``Host`` class takes care of calling Paramiko, the end-user should not directly
depend on Paramiko. In the future, we may replace it with for instance
twisted.conch.

At the top level, we usually have the interactive shell. But if a deployment
script is called as a library, it can have any other front-end. The built-in
interactive shell also has a telnet server (remote shell) and a shell which has
some multithreaded execution model (parallel deployment). These are realized
through Twisted Matrix, and there's some event-driven code touching the
iterative blocking code.
