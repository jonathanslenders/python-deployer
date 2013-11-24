import unittest

from deployer.console import Console
from deployer.pseudo_terminal import DummyPty


class ConsoleTest(unittest.TestCase):
    def test_print_warning(self):
        p = DummyPty()
        c = Console(p)
        c.warning('this is a warning')
        self.assertIn('this is a warning', p.get_output())

    def test_input(self):
        # Test normal input
        p = DummyPty(input_data='my-input\n')
        result = Console(p).input('input question')
        output = p.get_output()

        self.assertEqual(result, 'my-input')
        self.assertIn('input question', output)

        # Test default input
        p = DummyPty(input_data='\n')
        result = Console(p).input('input question', default='default-value')
        self.assertEqual(result, 'default-value')

        p = DummyPty(input_data='my-input\n')
        p.interactive = True # We have to set interactive=True, otherwise
                             # Console will take the default value anyway.
        result = Console(p).input('input question', default='default-value')
        self.assertEqual(result, 'my-input')

    def test_confirm(self):
        question = 'this is my question'

        # Test various inputs
        for inp, result in [
                ('yes', True),
                ('y', True),
                ('no', False),
                ('n', False) ]:

            p = DummyPty(input_data='%s\n' % inp)
            c = Console(p)
            returnvalue = c.confirm(question)

            self.assertEqual(returnvalue, result)
            self.assertIn(question, p.get_output())

        # Test default
        p = DummyPty(input_data='\n')
        c = Console(p)
        self.assertEqual(c.confirm('', default=True), True)
        self.assertEqual(c.confirm('', default=False), False)
