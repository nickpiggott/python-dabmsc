import socket
import time
import datetime
import logging

from msc.datagroups import Datagroup
from msc.packets import Packet

def elapsed_from_clock():
    last_requested = datetime.datetime.now()
    while True:
        now = datetime.datetime.now()
        yield now - last_requested
        last_requested = now

class NonBlockingTransportMixin:

    def clock(self): raise NotImplementedError()

class BlockingTransportMixin:
    """Defines a transport where the clock is set from the system clock elapsing"""

    def clock(self): return elapsed_from_clock().next

class UdpTransport(NonBlockingTransportMixin):
    """Send data over a UDP socket either as Datagroups or DAB Packets"""

    logger = logging.getLogger('msc.transports.udp')
    
    DATAGROUPS = 1
    PACKETS = 2
    
    @staticmethod
    def fromurl(url, logger=logger):
        """
        Parse this transport from its URI representation.

        This should be of the form:

            udp://<host>:<port>[?[parameter=value]...]

        Where a querystring may be specified in order to specify optional parameters.
        These parameters are defined as keyword arguments to the constructor.

        Currently, the following parameters are defined:

        * bitrate: transport bitrate in bps (default 16kbps)
        """
        from urlparse import urlparse, parse_qsl
        if isinstance(url, basestring): url = urlparse(url)
        if url.scheme != 'udp': raise ValueError('url must begin with the udp scheme')
        if url.path.find('?') >=0 : kwargs = dict(parse_qsl(url.path[url.path.index('?')+1:]))
        else: kwargs = dict(parse_qsl(url.query))

        return UdpTransport((url.hostname, url.port), logger=logger, **kwargs)
    
    def __init__(self, address, bitrate=16384, logger=logger):
        """
        address: UDP address as (host, port) tuple
        bitrate: bitrate to send data in bps
        """
        self.address = address
        self.logger.info('sending UDP frames to address: ${address}, bitrate={bitrate} bps'.format(address=address, bitrate=bitrate))
        self.bitrate = int(bitrate) if bitrate else bitrate
        self.logger = logger
        self.elapsed = datetime.timedelta(0)
        self.started = False
        
    def start(self, callback):
        if self.started: raise ValueError('transport already started')
        if not callback: raise ValueError('must define a valid callback')        
        self.logger.info('starting UDP sender with callback: %s', callback)

        self.started = True
        self.sock = socket.socket(socket.AF_INET, # Internet
                                  socket.SOCK_DGRAM) # UDP
        
        try:
            while self.started: 
                data = callback()
                if not isinstance(data, list): data = [data]
                for d in data:
                    b = d.tobytes()
                    if isinstance(d, Datagroup):
                        self.send_frame(b)
                        t = datetime.timedelta(milliseconds=(8 * float(len(b)) * 1000)/self.bitrate)
                        self.elapsed += t 
                        time.sleep(t.seconds + t.microseconds / 1e6)
                    elif isinstance(d, Packet):
                        self.send_frame(b)
                        t = datetime.timedelta(milliseconds=24)
                        self.elapsed += t 
                        time.sleep(t.seconds + t.microseconds / 1e6)
                    else: raise TypeError('neither a datagroup nor packet be this be: %s', type(d))
        finally: self.sock.close()

    def send_frame(self, data):
        self.sock.sendto(data, self.address)
    
    def stop(self):
        self.started = False

    def clock(self):
        class Iter:
            def __init__(self, transport):
                self.transport = transport
            def __iter__(self):
                return self
            def next(self):
                r = self.transport.elapsed
                self.transport.elapsed = datetime.timedelta(0)
                return r
        return Iter(self).next

    def __str__(self):
        return 'udp://{address}'.format(address=self.address)
                    
class FileTransport(NonBlockingTransportMixin):
    
    logger = logging.getLogger('msc.transports.file')

    @staticmethod
    def fromurl(url, logger=logger):
        """
        Parse this transport from its URI representation.

        This should be of the form:

            file:///<path>[?[parameter=value]...]

        Where a querystring may be specified in order to specify optional parameters.
        These parameters are defined as keyword arguments to the constructor.

        Currently, the following parameters are defined:

        * bitrate: transport bitrate in bps (default 8kbps)
        """
        from urlparse import urlparse, parse_qsl
        if isinstance(url, basestring): url = urlparse(url)
        if url.scheme != 'file': raise ValueError('url must begin with the file scheme')
        path = url.path[:url.path.index('?')] if url.path.find('?') >= 0 else url.path
        path = path.strip()
        if url.path.find('?') >= 0: kwargs = dict(parse_qsl(url.path[url.path.index('?')+1:]))
        else: kwargs = dict(parse_qsl(url.query))
        return FileTransport(open(path, 'wb'), logger=logger, **kwargs)

    def __init__(self, f, bitrate=8192, logger=logger):
        self.logger = logger
        self.logger.info('sending output to file: ${file}, bitrate={bitrate} bps'.format(file=f, bitrate=bitrate))
        self.f = f
        self.bitrate = int(bitrate) if bitrate else bitrate
        self.elapsed = datetime.timedelta(0)
        self.started = False
        self.notification = None

    def stop(self):
        self.started = False
    
    def start(self, callback):
        if self.started: raise ValueError('transport already started')
        if not callback: raise ValueError('must define a valid callback')        
        self.logger.info('starting file transport with callback: %s', callback)
        self.started = True
        try:
            while self.started: 
                data = callback()
                if not data: raise ValueError('no data or zero length data returned')
                if not isinstance(data, list): data = [data]
                for d in data: 
                    b = d.tobytes()
                    if isinstance(d, Datagroup):
                        self.f.write(b)
                        self.elapsed += datetime.timedelta(milliseconds=(8 * float(len(b)) * 1000)/self.bitrate)
                    elif isinstance(d, Packet):
                        self.f.write(b)
                        self.elapsed += datetime.timedelta(milliseconds=24)
                    else: raise TypeError('yarrgh. neither a datagroup nor packet this be: %s', type(d))
                self.f.flush()
        finally: self.f.close()

    def clock(self):
        class Iter:
            def __init__(self, transport):
                self.transport = transport
            def __iter__(self):
                return self
            def next(self):
                r = self.transport.elapsed
                self.transport.elapsed = datetime.timedelta(0)
                return r

        return Iter(self).next

    def __str__(self):
        return 'file://{path}'.format(path=self.path)
