import unittest
from mot import MotObject, ContentType
from msc.datagroups import decode_datagroups, encode_headermode, encode_directorymode , DatagroupType
from bitarray import bitarray
import logging
from bitarray.util import hex2ba


class Test(unittest.TestCase):

    def setUp(self) -> None:
        logging.basicConfig(level=logging.DEBUG)
        return super().setUp()

    def test_encode_short_headermode(self):
        """testing header mode with blank image"""
        
        # create MOT object
        object = MotObject(name = "TestObject", body = ("\x00" * 16).encode(), contenttype = ContentType.IMAGE_JFIF, transport_id = 12345)
        
        # encode object
        datagroups = encode_headermode([object])
        assert len(datagroups) == 2

        # test encoded datagroups
        datagroup_1 = datagroups[0] # header
        datagroup_2 = datagroups[1] # body

        assert len(datagroup_1.get_data()) == 22
        assert len(datagroup_1.tobytes()) == 31
        assert datagroup_1.get_type() == DatagroupType.HEADER
        assert datagroup_1.tobytes().hex() == '730080001230390014000001000a0401cc0b40546573744f626a6563749d93'  

        assert len(datagroup_2.tobytes()) == 27
        assert datagroup_2.get_type() == DatagroupType.BODY
        assert datagroup_2.tobytes().hex() == '740080001230390010000000000000000000000000000000002730'

    def test_roundtrip_1(self):
        hex_1 = '730080001230390014000001000a0401cc0b40546573744f626a6563749d93'
        hex_2 = '740080001230390010000000000000000000000000000000002730'
        data = bytes.fromhex(hex_1 + hex_2)
        datagroups = list(decode_datagroups(data))
        datagroup_1 = datagroups[0]
        datagroup_2 = datagroups[1]
        assert datagroup_1.tobytes().hex() == hex_1
        assert datagroup_2.tobytes().hex() == hex_2
            
    def test_encode_short_directorymode(self):
        """testing directory mode with blank images"""
        
        # create MOT objects
        objects = []
        for i in range(3):
            object = MotObject("TestObject%d" % i, ("\x00" * 16).encode(), contenttype = ContentType.IMAGE_JFIF, transport_id = 12345)
            objects.append(object)
            
        # encode directory 
        datagroups = encode_directorymode(objects)
        assert len(datagroups) == 4

        # TODO test encoded datagroups
        datagroup_1 = datagroups[0] # directory
        datagroup_2 = datagroups[1] # object 1
        datagroup_3 = datagroups[2] # object 2
        datagroup_4 = datagroups[3] # object 3

    def test_decode_short_headermode(self):

        header_bytes = bytes.fromhex('730080001230390014000001000a0401cc0b40546573744f626a6563749d93')
        body_bytes = bytes.fromhex('740080001230390010000000000000000000000000000000002730')
        datagroups = list(decode_datagroups(header_bytes + body_bytes))
        datagroup_1 = datagroups[0]
        datagroup_2 = datagroups[1]
        
        assert datagroup_1.get_type() == DatagroupType.HEADER
        assert datagroup_1.get_transport_id() == 12345
        assert datagroup_1.get_segment_index() == 0
        assert datagroup_1.get_continuity() == 0
        assert datagroup_1.get_last() == True

        assert datagroup_2.get_type() == DatagroupType.BODY
        assert datagroup_2.get_transport_id() == 12345
        assert datagroup_2.get_segment_index() == 0
        assert datagroup_2.get_continuity() == 0
        assert datagroup_2.get_last() == True

    def test_decode_from_file(self):

        """
        Test decoding of datagroups from a file-like object
        """

        header_bytes = bytes.fromhex('730080001230390014000001000a0401cc0b40546573744f626a6563749d93')
        body_bytes = bytes.fromhex('740080001230390010000000000000000000000000000000002730')

        import io
        f = io.BytesIO(header_bytes + body_bytes)
        datagroups = list(decode_datagroups(f))

        assert datagroups[0].tobytes() == header_bytes
        assert datagroups[1].tobytes() == body_bytes


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    #unittest.main()
    test = Test()
    test.test_decode_from_file()

