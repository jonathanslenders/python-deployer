
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

class BooleanOption(Option):
    def __init__(self, current_value):
        assert isinstance(current_value, bool)
        Option.__init__(self, ['on', 'off'], 'on' if current_value else 'off')

    def get_value_as_bool(self):
        return self._value == 'on'


class Options(object):
    def __init__(self):
        self._options = {
            'keep-panes-open': BooleanOption(False),

            # Other options to implement:
            #    'colorscheme': Option(['dark_background', 'light_background'], 'dark_background'),
            #    'interactive': BooleanOption(True),
            #    'interactive': BooleanOption(True),
        }

    def __getitem__(self, name):
        return self._options[name]

    def items(self):
        return self._options.items()

