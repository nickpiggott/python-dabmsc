import unittest
from mot import MotObject, ContentType
from msc.datagroups import *
from msc.packets import *
from bitarray import bitarray

class Test(unittest.TestCase):

    def test_blank_headermode(self):

        # create MOT object
        object = MotObject(name = "TestObject", body = ("\x00" * 128).encode(), contenttype = ContentType.IMAGE_JFIF, transport_id = 12345)
        
        # encode to datagroups
        datagroups = encode_headermode([object])
        
        # encode to packets
        packets = encode_packets(datagroups, 1, PacketSize.SIZE_96)
        
        assert len(packets) == 3
        
        packet_1 = packets[0]
        packet_2 = packets[1]
        packet_3 = packets[2]
                                            
        assert packet_1.tobytes().hex() == 'cc011f730080001230390014000008000a0401cc0b40546573744f626a6563749ccd0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000009a56'
        assert packet_2.tobytes().hex() == 'd8015b740080001230390080000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001f29'
        assert packet_3.tobytes().hex() == 'e4013000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000150e00000000000000000000000000000000000000000000000000000000000000000000000000000000000000d5ed'


    def test_roundtrip_1(self):

        packet_1 = 'cc011f730080001230390014000008000a0401cc0b40546573744f626a6563749ccd0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000009a56'
        packet_2 = 'd8015b740080001230390080000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001f29'
        packet_3 = 'e4013000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000150e00000000000000000000000000000000000000000000000000000000000000000000000000000000000000d5ed'
        
        packets = list(decode_packets(bytes.fromhex(packet_1 + packet_2 + packet_3)))

        assert len(packets) == 3
        p1 = packets[0]
        p2 = packets[1]
        p3 = packets[2]

        assert p1.get_size() == PacketSize.SIZE_96
        assert p1.get_address() == 1
        assert p1.is_first() == True
        assert p1.is_last() == True
        assert len(p1.get_data()) == 31

        assert p2.get_size() == PacketSize.SIZE_96
        assert p2.get_address() == 1
        assert p2.is_first() == True
        assert p2.is_last() == False
        assert p2.get_index() == 1
        assert len(p2.get_data()) == 91

        assert p3.get_size() == PacketSize.SIZE_96
        assert p3.get_address() == 1
        assert p3.is_first() == False
        assert p3.is_last() == True
        assert p3.get_index() == 2
        assert len(p3.get_data()) == 48

        assert p1.tobytes().hex() == packet_1
        assert p2.tobytes().hex() == packet_2
        assert p3.tobytes().hex() == packet_3

    def test_decode_from_file(self):

        """
        Test decoding of packets from a file-like object
        """

        packet_1 = 'cc011f730080001230390014000008000a0401cc0b40546573744f626a6563749ccd0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000009a56'
        packet_2 = 'd8015b740080001230390080000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001f29'
        packet_3 = 'e4013000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000150e00000000000000000000000000000000000000000000000000000000000000000000000000000000000000d5ed'
        
        import io
        f = io.BytesIO(bytes.fromhex(packet_1 + packet_2 + packet_3))
        packets = list(decode_packets(f))

        assert len(packets) == 3
        p1 = packets[0]
        p2 = packets[1]
        p3 = packets[2]

        assert p1.get_size() == PacketSize.SIZE_96
        assert p1.get_address() == 1
        assert p1.is_first() == True
        assert p1.is_last() == True
        assert len(p1.get_data()) == 31

        assert p2.get_size() == PacketSize.SIZE_96
        assert p2.get_address() == 1
        assert p2.is_first() == True
        assert p2.is_last() == False
        assert p2.get_index() == 1
        assert len(p2.get_data()) == 91

        assert p3.get_size() == PacketSize.SIZE_96
        assert p3.get_address() == 1
        assert p3.is_first() == False
        assert p3.is_last() == True
        assert p3.get_index() == 2
        assert len(p3.get_data()) == 48

        assert p1.tobytes().hex() == packet_1
        assert p2.tobytes().hex() == packet_2
        assert p3.tobytes().hex() == packet_3

if __name__ == "__main__":
    import logging
    #logging.basicConfig(level=logging.DEBUG)
    unittest.main()
