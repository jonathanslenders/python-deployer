Changelog
=========


Now
---

?

Version 0.3.1: 21 november 2013
-------------------------------

- Built-in SCP shell added (with following commands:
    lpwd stat ledit lstat edit clear get lcd cd connect lls pwd exit ls
    lconnect put lview view)
- HostsContainer.get/put was renamed to HostsContainer.get_file/put_file
- Sets are now the preferred way of writing a lists of hosts to a Host
  definition. Tuples are still allowed, lists are not allowed anymore.
- Better exception handling in the command line shell
- Improved progress bar widget
- Progress bar used for SSH connection.
- Progress bars for uploading and downloading data.
- getcwd(), stat() and listdir_stat() functions added to Host
- A lot of refactoring, mainly in host and host_container.
- A lot of bugfixes.


Missing pieces
---------------
We don't have a real changelog from before november 2013.


Summer 2011, somewher.
----------------------
- First initial, working version.
