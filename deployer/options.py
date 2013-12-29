
"""
Runtime options.
"""


class Option(object):
    """
    Shell option.
    """
    def __init__(self, values, current_value):
        self.values = values
        self._value = current_value
        self._callbacks = []

    def on_change(self, callback):
        self._callbacks.append(callback)

    def get(self):
        return self._value

    def set(self, value):
        self._value = value
        for c in self._callbacks:
            c()


class Options(object):
    def __init__(self):
        self._options = {
            'colorscheme': Option(['dark_background', 'light_background'], 'dark_background'),
            'keep-panes-open': Option(['on', 'off'], 'off'),
            'interactive': Option(['on', 'off'], 'on'),
        }

    def __getitem__(self, name):
        return self._options[name]

    def items(self):
        return self._options.items()

