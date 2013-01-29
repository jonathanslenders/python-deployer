from __future__ import absolute_import

from deployer.loggers import Logger
from threading import Thread, Event

import irc.client
import socket

# NOTE: in order to use this logger, make sure that your IRC servers have the
#       following settings:
#
# - Connections per IP: large enough or unlimited. (at least one per client.)
# - Throttle time: 0  (or low enough)



class IRCLogger(Logger):
    def __init__(self, host, port=6667, channel='#deploy', ircname='Deployer'):
        self.backend_params = (host, port, channel, ircname)

    def attached_first(self):
        self.backend = IRCLoggerBackend(* self.backend_params)
        self.backend.start()

    def detached_last(self):
        self.backend.stop()

    def log_cli_action(self, action_entry):
        command = action_entry.command
        self.backend.log_data(command)
        return Logger.log_cli_action(self, action_entry)


class IRCLoggerBackend(object):
    """
    This class is not the IRC logger itself, but its create_logger-method will produce
    a logger. (This way we can share one IRC connection between multiple parrallel threads.)
    """
    def __init__(self, host, port, channel, ircname):
        self.channel = channel
        self.connection = None
        self.nickname = 'deployer'
        self.nickname_index = 0

        self.client = irc.client.IRC()
        try:
            c = self.client.server().connect(host, port, self.nickname)
        except irc.client.ServerConnectionError, x:
            print x

        c.add_global_handler("welcome", self.on_connect)
        c.add_global_handler("privmsg", self.on_privmsg)
        c.add_global_handler("nicknameinuse", self.on_nicknameinuse)

    def start(self):
        """
        Start event loop when attached.
        """
        stop_event = Event()
        class loop(Thread):
            def run(thread):
                #while thread.keep_running:
                while not stop_event.is_set():
                    self.client.process_once(timeout=.5)

            def stop(thread):
                stop_event.set()

        self._loop = loop()
        self._loop.setDaemon(True)
        self._loop.start()

    def stop(self):
        self._loop.stop()

    def on_connect(self, connection, event):
        """
        Connection with IRC server established.
        """
        # Join channel.
        if irc.client.is_channel(self.channel):
            connection.join(self.channel)
        self.connection = connection

    def on_privmsg(self, connection, event):
        """
        Private message received.
        """
        # Answer.
        fqdn = socket.getfqdn()
        connection.privmsg(self.channel, "I'm the deployer, running on %s" % fqdn)
        #connection.privmsg(self.channel, "You said: " + event.arguments()[0])

    def on_nicknameinuse(self, connection, event):
        """
        Nickname is already in use.
        """
        # Choose another nick.
        self.nickname_index += 1
        connection.nick('%s%s' % (self.nickname, self.nickname_index))

    def log_data(self, data):
        """
        Logging of data -> writing op message in IRC channel.
        """
        if self.client and self.connection:
            self.connection.privmsg(self.channel, data)

    def create_logger(self):
        """
        Spawn logger instance.
        """
        return _IRCLogger(self)
