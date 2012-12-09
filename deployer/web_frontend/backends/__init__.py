import crypt
import random
import redis
import string


"""
Database scheme:

    === Users ===
users : [ (list of usernames) ]
user:(username):password  : (crypted-password)

"""


class Backend(object):
    def authenticate(self, username, password):
        return False

    def create_user(self, username, password):
        pass

    def set_password(self, username, password):
        pass

    def delete_user(self, username):
        pass

    def get_users(self):
        return []


class RedisBackend(Backend):
    """
    Redis storage backend for the web deployer.
    """
    def __init__(self, host='localhost', port=2000, password=None):
        self.redis = redis.Redis(host, port, password=password)

    def authenticate(self, username, password):
        """
        Authentication, return True when valid credetials are given.
        """
        if not self.redis.sismember('users', username):
            return False

        crypted = self.redis.get('users:%s:password' % username)
        return crypted and crypt.crypt(password, crypted) == crypted

    def create_user(self, username, password):
        """
        Change password for this user.
        """
        self.redis.sadd('users', username)
        salt = ''.join(random.sample(string.ascii_letters, 8))
        crypted = crypt.crypt(password, salt)
        return self.redis.set('users:%s:password' % username, crypted)

    set_password = create_user

    def delete_user(self, username):
        self.redis.srem('users', username)
        self.redis.delete('users:%s:password' % username)

    def get_users(self):
        """ List all users """
        return self.redis.smembers('users')
