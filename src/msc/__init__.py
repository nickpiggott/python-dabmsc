import crcmod
from bitarray import bitarray
import logging

logger = logging.getLogger('msc')

crcfun = crcmod.mkCrcFun(0x11021, 0x0, False, 0xFFFF)
def calculate_crc(data):
    return crcfun(data)

def hex_to_bitarray(hex):
    b = bitarray()
    for byte in hex.split(' '):
        b.extend(int_to_bitarray(int('0x%s' % byte, 16), 8))
    return b

def int_to_bitarray(i, n):
    return bitarray(('{0:0%db}' % n).format(i))

def bitarray_to_int(bits):
    return int(bits.to01(), 2)

def bitarray_to_hex(bits, width=32):
    if not isinstance(bits, bitarray): raise ValueError('object is not a bitarray')
    rows = []
    for i in range(0, len(bits), width*8):
        rows.append(' '.join(["%02X" % ord(x) for x in bits[i:i+(width*8)].tobytes()]).strip())
    return '\r\n'.join(rows)

def bitarray_to_binary(bits, width=32):
    if not isinstance(bits, bitarray): raise ValueError('object is not a bitarray')
    rows = []
    for i in range(0, len(bits), width*8):
        bytes = []
        for j in range(i, i+(width*8), 8):
            bytes.append(bits[j:j+8].to01())
        rows.append(' '.join(bytes))
    return '\r\n'.join(rows)

class InvalidCrcError(Exception): 
    
    def __init__(self, crc, data):
        self.crc = crc
        self.data = data

class TransportIdGenerator():
    '''interface for classes to generate transport IDs'''

    def next(self, name=None):
        pass

    def exists(self, id):
        pass

class MemoryCachedTransportIdGenerator(TransportIdGenerator):
    '''generates transport IDs cached in memory'''

    def __init__(self):
        self.ids = []
        self.cache = {}

    def next(self, name=None):
        # first check the cache
        if name is not None and self.cache.has_key(name):
            return self.cache.get(name)

        # if we've run out then start recycling from the head
        if len(self.ids) >= (1 << 16) - 1: return self.ids.pop(0)
        import random
        id = None
        while id is None or id in self.ids:
            id = int(random.random() * (1 << 16))
        self.ids.append(id)
        if name is not None: self.cache[name] = id

        return id

# default transport ID generator
transport_id_generator = MemoryCachedTransportIdGenerator()
def generate_transport_id(name=None):
    return transport_id_generator.next(name)
