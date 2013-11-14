from deployer.contrib.default_config import example_settings
from deployer.node import Env
import unittest


class ExampleConfigTest(unittest.TestCase):
    def test_assignments_to_node(self):
        env = Env(example_settings())
        self.assertEqual(env.examples.return_hello_world(), 'Hello world')
