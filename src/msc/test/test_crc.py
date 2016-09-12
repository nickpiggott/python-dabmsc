from msc import calculate_crc
import unittest

class Test(unittest.TestCase):

    def test_crc_checksum(self):
        """
        Classic CRC check

        http://reveng.sourceforge.net/crc-catalogue/16.htm
        """
        assert(calculate_crc("123456789") == 0x906e)

if __name__ == "__main__":
    unittest.main()
