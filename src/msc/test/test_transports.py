import unittest
import urllib2

from msc import calculate_crc
from mot import MotObject, ContentType
from msc.datagroups import encode_headermode
from msc.transports import UdpTransport, FileTransport

url = 'http://owdo.thisisglobal.com/2.0/id/25/logo/320x240.jpg'
        
class UdpTransportTest(unittest.TestCase):
    
    def test_fromurl(self):
        transport = UdpTransport.fromurl('udp://10.15.81.160:5555/?bitrate=8192')
        
    def test_encode(self):
        
        req = urllib2.Request(url)
        response = urllib2.urlopen(req)
        data = response.read()
        type = ContentType.IMAGE_JFIF
                
        # create MOT object
        object = MotObject(url, data, type)
            
        # encode object
        datagroups = encode_headermode([object])

        # define callback
        i = iter(datagroups)
        def callback():
            return i.next()

        transport = UdpTransport(address=('10.15.81.160', 5555))
        transport.start(callback)       

        
class FileTransportTest(unittest.TestCase):
    
    def test_fromurl(self):
        import os
        transport = FileTransport.fromurl('file:///%s/out.dat' % os.path.curdir)

    def test_encode_slide_to_file(self):
        url = 'http://owdo.thisisglobal.com/2.0/id/25/logo/320x240.jpg'
        req = urllib2.Request(url)
        response = urllib2.urlopen(req)
        data = response.read()
        type = ContentType.IMAGE_JFIF
                
        # create MOT object
        object = MotObject(url, data, type)
            
        # encode object
        datagroups = encode_headermode([object])

        # define callback
        i = iter(datagroups)
        def callback():
            return i.next()

        import StringIO
        s = StringIO.StringIO()
        transport = FileTransport(s)
        transport.start(callback)       


if __name__ == "__main__":
    unittest.main()
