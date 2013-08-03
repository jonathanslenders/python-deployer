.. _internals:

Internals
=========

Roughly, this is the current flow from the interactive shell untill the actual
SSH client.

TODO: more in depth: more explanation, ...


.. graphviz::

   digraph internals{
       "Host" [shape=box];
       "HostContainer" [shape=box];
       "HostsContainer" [shape=box];
       "Node" [shape=box];
       "SimpleNode" [shape=box];
       "Env" [shape=box];
       "HostContext" [shape=box];

       "Host" -> "HostContext";
       "Host" -> "Paramiko (SSH)";
       "HostsContainer" -> "Host";
       "HostContainer" -> "Host";
       "HostsContainer" -> "HostContext";
       "HostContainer" -> "HostContext";
       "Node" -> "HostsContainer";
       "SimpleNode" -> "HostsContainer";
       "SimpleNode" -> "HostContainer";
       "Env" -> "Node";
       "Env" -> "SimpleNode";
       "Interactive shell" -> "Env";
   }

