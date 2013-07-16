import types

def isclass(obj):
    """
    Helper.

    Identical to Python 2.7 's inspect.isclass.
    isclass in Python 2.6 also returns True when
    the passed object has a __bases__ attribute.
    (like in case of an instance.)
    """
    return isinstance(obj, (type, types.ClassType))

from .network import *
from .string_utils import *
