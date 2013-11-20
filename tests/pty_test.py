import unittest

from deployer.pseudo_terminal import Pty

class PtyTest(unittest.TestCase):
    def test_get_size(self):
        # Create pty from standard stdin/stdout
        p = Pty()

        # Test get_size -> returns height,width
        size = p.get_size()
        self.assertIsInstance(size, tuple)
        self.assertEqual(len(size), 2)
        self.assertIsInstance(size[0], int)
        self.assertIsInstance(size[1], int)

        # Test get_width
        width = p.get_width()
        self.assertIsInstance(width, int)
        self.assertEqual(width, size[1])

        # Test get_height
        height = p.get_height()
        self.assertIsInstance(height, int)
        self.assertEqual(height, size[0])
