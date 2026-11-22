import unittest

def utilization(rx_bps, tx_bps, capacity_bps):
    if capacity_bps <= 0:
        raise ValueError('capacity must be positive')
    return max(rx_bps, tx_bps) / capacity_bps * 100

class CapacityTests(unittest.TestCase):
    def test_80_percent(self):
        self.assertEqual(utilization(2e9,8e9,10e9),80)
    def test_invalid_capacity(self):
        with self.assertRaises(ValueError):
            utilization(1,1,0)
if __name__ == '__main__': unittest.main()
