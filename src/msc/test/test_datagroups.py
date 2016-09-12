import unittest
from mot import MotObject, ContentType
from msc import bitarray_to_hex
from msc.datagroups import encode_headermode, encode_directorymode 
from bitarray import bitarray

class Test(unittest.TestCase):

    def test_blank_headermode(self):
        """testing header mode with blank image"""
        
        # create MOT object
        print 'creating MOT object'
        object = MotObject("TestObject", "\x00" * 1024, ContentType.IMAGE_JFIF)
        
        # encode object
        datagroups = encode_headermode([object])
        
        for datagroup in datagroups:
            tmp = bitarray()
            tmp.frombytes(datagroup.tobytes())
            # TODO test bytes
            
    def test_blank_directorymode(self):
        """testing directory mode with blank images"""
        
        # create MOT objects
        objects = []
        for i in range(3):
            object = MotObject("TestObject%d" % i, "\x00" * 1024, ContentType.IMAGE_JFIF)
            objects.append(object)
            
        # encode object
        datagroups = encode_directorymode(objects)
        
        for datagroup in datagroups:
            tmp = bitarray()
            tmp.frombytes(datagroup.tobytes())
            # TODO test bytes

if __name__ == "__main__":
    unittest.main()
