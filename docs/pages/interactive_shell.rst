.. _interactive-shell:


The interactive shell
=====================

It's very easy to create an interactive command line shell from a node tree.
Suppose that you have a `deployer.node.Node` called ``MyRootNode``, then you
can create a shell by making an executable file like this:

::

    #!/usr/bin/env python
    from deployer.client import start
    from deployer.node import Node

    class MyRootNode(Node):
        ...

    if __name__ == '__main__':
        start(MyRootNode)

If you save this as ``client.py`` and call it by typing ``python ./client.py
--help``, the following help text will be shown:

::

    Usage:
      ./client.py run [-s | --single-threaded | --socket SOCKET] [--path PATH]
                      [--non-interactive] [--log LOGFILE]
                      [--] [ACTION PARAMETER...]
      ./client.py listen [--log LOGFILE] [--non-interactive] [--socket SOCKET]
      ./client.py connect (--socket SOCKET) [--path PATH] [--] [ACTION PARAMETER...]
      ./client.py telnet-server [--port PORT] [--log LOGFILE] [--non-interactive]
      ./client.py list-sessions
      ./client.py -h | --help
      ./client.py --version

    Options:
      -h, --help             : Display this help text.
      -s, --single-threaded  : Single threaded mode.
      --path PATH            : Start the shell at the node with this location.
      --non-interactive      : If possible, run script with as few interactions as
                               possible.  This will always choose the default
                               options when asked for questions.
      --log LOGFILE          : Write logging info to this file. (For debugging.)
      --socket SOCKET        : The path of the unix socket.
      --version              : Show version information.

There are several options to start such a shell. It can be multi or single
threaded, or you can run it as a telnet-server. Normally, you just type the
following to get the interactive prompt:

::

    ./client.py run


Navigation
----------

Navigation is very similar to navigating in a Bash shell.

+-------------+--------------------------------------------------------------+
| Command     | Meaning                                                      |
+=============+==============================================================+
| ``cd``      | ``cd node_name`` will move to a certain node. ``cd -`` will  |
|             | move back to the previous node. ``cd ..`` will move to the   |
|             | and ``cd /`` will move to the root node. It's the same as a  |
|             | Bash shell, except that spaces are used instead of slashes   |
|             | when several nodes are chained, e.g. ``cd node childnode``.  |
+-------------+--------------------------------------------------------------+
| ``ls``      | Move to a certain node                                       |
+-------------+--------------------------------------------------------------+
| ``pwd``     | Print current node (directory)                               |
+-------------+--------------------------------------------------------------+
| ``find``    | Recursively list all the childnode. Press ``q`` to quit the  |
|             | pager.                                                       |
+-------------+--------------------------------------------------------------+
| ``exit``    | Leave the deployment shell.                                  |
+-------------+--------------------------------------------------------------+
| ``clear``   | Clear the screen.                                            |
+-------------+--------------------------------------------------------------+

Running node actions
--------------------

In order to execute an action of the current node, just type the name of the
action and press enter. Follow the action name by a space and a value if you
want to pass that value as parameter.

Sandboxed execution is possible by preceding the action name by the word
``sandbox``. e.g. type: ``sandbox do_something param``. This will run the
action, like usual, but it won't execute the actual commands on the hosts,
instead it will execute a syntax-checking command instead.


Special commands
----------------

Some special commands, starting with double dash:

+---------------------+--------------------------------------------------------+
| Command             | Meaning                                                |
+=====================+========================================================+
| ``--inspect``       | Show information about the current node.               |
|                     |                                                        |
|                     | This displays the file where the node has been defined,|
|                     | the hosts that are bound to this node and the list of  |
|                     | actions child nodes that it contains.                  |
+---------------------+--------------------------------------------------------+
| ``--source-code``   | Display the source code of the current node.           |
+---------------------+--------------------------------------------------------+
| ``--connect``       | Open an interactive (bash) shell on a host of this     |
|                     | node. It will ask which host to connect if there are   |
|                     | several hosts in this node.                            |
+---------------------+--------------------------------------------------------+
| ``--version``       | Show version information.                              |
+---------------------+--------------------------------------------------------+
| ``--scp``           | Open an SCP shell.                                     |
+---------------------+--------------------------------------------------------+
| ``--run``           | Run a shell command on all hosts in the current node.  |
+---------------------+--------------------------------------------------------+
| ``--run-with-sudo`` | Identical to ``--run``, but using ``sudo``             |
+---------------------+--------------------------------------------------------+

For ``--inspect``, ``--source-code`` and ``--connect``, it's possible to pass
the name or path of another node as parameter. E.g.:  ``--connect node
child_node``.

The SCP (secure copy) shell
---------------------------

Typing ``--scp`` in the main shell will open a subshell in which you can run
SCP commands. This is useful for manually downloading and uploading files to
servers.

+-----------------+---------------------+---------------------------------------+
| Where           | Command             | Meaning                               |
+=================+=====================+=======================================+
| Remote          | ``cd`` <directory>  | Go to another directory at the server.|
|                 +---------------------+---------------------------------------+
|                 | ``pwd``             | Print working directory at the server.|
|                 +---------------------+---------------------------------------+
|                 | ``stat`` <file>     | Print information about file or       |
|                 |                     | directory on the server.              |
|                 +---------------------+---------------------------------------+
|                 | ``edit`` <file>     | Open this file in an editor (vim)     |
|                 |                     | on the server.                        |
|                 +---------------------+---------------------------------------+
|                 | ``connect``         | Open interactive (bash) shell at the  |
|                 |                     | at the server.                        |
+-----------------+---------------------+---------------------------------------+
| Local           | ``lcd`` <directory> | Go locally to another directory.      |
|                 +---------------------+---------------------------------------+
|                 | ``lpwd``            | Print local working directory.        |
|                 +---------------------+---------------------------------------+
|                 | ``lstat`` <file>    | Print information about a local file  |
|                 |                     | or directory.                         |
|                 +---------------------+---------------------------------------+
|                 | ``ledit`` <file>    | Open this local file in an editor     |
|                 +---------------------+---------------------------------------+
|                 | ``lconnect``        | Open local interactive (bash) shell   |
|                 |                     | at this directory.                    |
+-----------------+---------------------+---------------------------------------+
| File operations | ``put`` <file>      | Upload this local file to the server. |
|                 +---------------------+---------------------------------------+
|                 | ``get`` <file>      | Download remote file from the server. |
+-----------------+---------------------+---------------------------------------+
| Other           | ``exit``            | Return to the main shell.             |
|                 +---------------------+---------------------------------------+
|                 | ``clear``           | Clear screen.                         |
+-----------------+---------------------+---------------------------------------+


Implementing a custom shell
---------------------------

TODO
