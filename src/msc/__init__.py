import crcmod
from bitarray import bitarray
import logging

logger = logging.getLogger('msc')

crcfun = crcmod.mkCrcFun(0x11021, 0x0, False, 0xFFFF)

def calculate_crc(data) -> int:
    logger.debug('calculating CRC from %d bytes: %s', len(data), data.hex())
    return crcfun(data)

class InvalidCrcError(Exception): 
    
    def __init__(self, calculated : int, signalled : int):
        self.calculated = calculated
        self.signalled = signalled

    def __str__(self) -> str:
        return "calculated CRC %x is different from signalled %x" % (self.calculated, self.signalled)

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
        if name is not None and name in self.cache:
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
