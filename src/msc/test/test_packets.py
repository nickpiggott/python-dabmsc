import unittest
from mot import MotObject, ContentType
from msc.datagroups import *
from msc.packets import *
from bitarray import bitarray

class Test(unittest.TestCase):

    def test_blank_headermode(self):
        data = ("\x00" * 128).encode()
        
        # create MOT object
        object = MotObject("TestObject", data, ContentType.IMAGE_JFIF)
        
        # encode to datagroups
        datagroups = encode_headermode([object])
        
        # encode to packets
        packets = encode_packets(datagroups, 1, Packet.SIZE_96)
        
        for packet in packets:
            tmp = bitarray()
            tmp.frombytes(packet.tobytes())
            # TODO test packet bytes


if __name__ == "__main__":
    unittest.main()
