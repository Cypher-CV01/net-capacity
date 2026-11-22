import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services'))
from snmp_host import calculate_rate

class TestCounterRates(unittest.TestCase):
    def setUp(self):
        self.a = {'monotonic': 100, 'uptime': 1000, 'status': 1, 'in': 1000, 'out': 2000}
        self.b = {'monotonic': 160, 'uptime': 7000, 'status': 1, 'in': 1000 + 750000000, 'out': 2000 + 375000000}
    def test_valid(self):
        self.assertEqual(calculate_rate(self.a, self.b, 10_000_000_000), (100_000_000, 50_000_000))
    def test_first_sample(self):
        self.assertIsNone(calculate_rate(None, self.b, 10_000_000_000))
    def test_reset(self):
        self.assertIsNone(calculate_rate(self.b, self.a, 10_000_000_000))
    def test_link_down(self):
        self.b['status'] = 2
        self.assertIsNone(calculate_rate(self.a, self.b, 10_000_000_000))

if __name__ == '__main__':
    unittest.main()
