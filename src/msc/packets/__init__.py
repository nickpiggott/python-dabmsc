from bitarray import bitarray
from msc import bitarray_to_hex, int_to_bitarray, calculate_crc, InvalidCrcError
import logging

logger = logging.getLogger('dabdata.packets')

class IncompletePacketError(Exception):
    pass

class Packet:
    
    SIZE_96 = 96
    SIZE_72 = 72
    SIZE_48 = 48
    SIZE_24 = 24
    sizes = [SIZE_24, SIZE_48, SIZE_72, SIZE_96]
    
    def __init__(self, size, address, data, first, last, index):
        self.size = size
        self.address = address
        self.data = data
        self.first = first
        self.last = last
        self.index = index
        
    def tobytes(self):
        
        bits = bitarray()
        
        # build header
        bits += int_to_bitarray((self.size / 24) - 1, 2) # (0-1): packet length
        bits += int_to_bitarray(self.index, 2) # (2-3): continuity index
        bits += bitarray('1' if self.first else '0') # (4): first packet of datagroup series
        bits += bitarray('1' if self.last else '0') # (5): last packet of datagroup series
        bits += int_to_bitarray(self.address, 10) # (6-15): packet address
        bits += bitarray('0') # (16): Command flag = 0 (data)
        bits += int_to_bitarray(len(self.data), 7) # (17-23): useful data length

        # add the packet data
        tmp = bitarray()
        if len(self.data) > 0:
            tmp.frombytes(self.data)
            bits += tmp # (24-n): packet data
                    
        # add packet padding if needed
        bits += bitarray('0'*(self.size - len(self.data) - 5)*8)
        
        # add CRC
        bits += int_to_bitarray(calculate_crc(bits.tobytes()), 16)
        
        return bits.tobytes()

    @staticmethod
    def frombits(bits, i=0, check_crc=True):
        """Parse a packet from a bitarray, with an optional offset"""
        
        size = (int(bits[i+0:i+2].to01(), 2) + 1) * 24
        if (len(bits) - i) < (size * 8): raise IncompletePacketError('length of bitarray is less than passed data length %d bytes < %d bytes', len(bits) / 8, size)
        index = int(bits[i+2:i+4].to01(), 2)
        first = bits[i+4]
        last = bits[i+5]
        address = int(bits[i+6:i+16].to01(), 2)
        data_length = int(bits[i+17:i+24].to01(), 2)
        data = bits[i+24:i+24+(data_length*8)]
        crc = int(bits[i + (size * 8) - 16 : i + (size * 8)].to01(), 2)
        if check_crc:        
            calculated = calculate_crc(bits[i + 0 : i +(size * 8) - 16].tobytes())
            if crc != calculated:
                raise InvalidCrcError(crc, bits[i + 0 : i +(size * 8)].tobytes())
        packet = Packet(size, address, data.tobytes(), first, last, index)
        logger.debug('parsed packet: %s', packet)
        
        return packet
        
    def __str__(self):
        return 'size=%d, address=%d, first=%s, last=%s, index=%d, data=%d bytes' % (self.size, self.address, self.first, self.last, self.index, len(self.data))
        
    def __repr__(self):
        return '<Packet: %s>' % str(self)

def encode_packets(datagroups, address=None, size=None, continuity=None, padding=False):

    """
    Encode a set of datagroups into packets
    """

    def get_continuity_index(address):
        index=0
        if address in continuity:
            index = continuity[address]
            index += 1
            if index > 3: index = 0
        continuity[address] = index
        return index

    def get_required_size(payload_size, max_packet_size):
        if payload_size > (max_packet_size-5):
          return max_packet_size
        if payload_size > (72-5):
          return Packet.SIZE_96
        elif payload_size > (48-5):
          return Packet.SIZE_72
        elif payload_size > (24-5):
          return Packet.SIZE_48
        else:
          return Packet.SIZE_24 
          
    if not address: address = 1
    if not size: size = Packet.SIZE_96
    if not continuity: continuity = {}
    if not padding: padding = False

    if address < 1 or address > 1024: raise ValueError('packet address must be greater than zero and less than 1024')
    if size not in Packet.sizes: raise ValueError('packet size %d must be one of: %s' % (size, Packet.sizes))
    
    packets = []
    
    # encode the datagroups into a continuous datastream
    # repeating sufficient times to make sure the final continuity index is 3
    # this could make the output filesize x2 or x4 the minimum size
    while True:
        for datagroup in datagroups:
            data = datagroup.tobytes()
            chunk_size = size - 5
            for i in range(0, len(data), chunk_size):
                chunk = data[i:i+chunk_size if i+chunk_size < len(data) else len(data)]
                continuity_index = get_continuity_index(address)
                packet = Packet(get_required_size(len(chunk),size), address, chunk, True if i == 0 else False, True if i+chunk_size >= len(data) else False, continuity_index)
                packets.append(packet)
        if padding == False or (padding == True and continuity_index == 3):
            break
        # add padding packets to make sure the Continuity Index ends with 3
        # if padding and continuity_index != 3:
        #    while continuity_index !=3:
        #        continuity_index += 1
        #        packet = Packet(size, address, [], True, True, continuity_index)
        #        packets.append(packet)
        
    return packets

def decode_packets(data, error_callback=None, check_crc=True, resync=True):

    """
    Generator function to decode packets from a bitstream

    The bitstream may be presented as either a bitarray, a file object or a socket
    """
       
    if isinstance(data, bitarray):
        logger.debug('decoding packets from bitarray')
        i = 0
        while i < len(data):
            while i < len(data):
                if len(data) < 2: break
                size = (int(data[i:i+2].to01(), 2) + 1) * 24
                if len(data) < (size * 8): break
                try:
                    packet = Packet.frombits(data, i=i, check_crc=check_crc)
                    yield packet
                    i += (size * 8)
                except (InvalidCrcError, ice):
                    if error_callback: error_callback(ice) 
                    if resync: i += 8
                    else: i += (size * 8)
    elif hasattr(data, 'read'):
        logger.debug('decoding packets from file: %s', data)
        buf = bitarray()  
        r = data.read(1024)
        while len(r):
            buf.frombytes(r)
            logger.debug('chunking buffer of length %d bytes', len(buf)/8)
            i = 0
            while i < len(buf):
                if len(buf) < 2: break
                size = (int(buf[i:i+2].to01(), 2) + 1) * 24
                if len(buf) < (size * 8): break
                try:
                    packet = Packet.frombits(buf, i=i, check_crc=check_crc)
                    yield packet
                    i += (size * 8)
                except IncompletePacketError: 
                    break
                except (InvalidCrcError, ice):
                    if error_callback: error_callback(ice) 
                    if resync: i += 8
                    else: i += (size * 8)
            buf = buf[i:]
            r = data.read(1024)
    elif hasattr(data, 'recv'):
        data.setblocking(True)
        logger.debug('decoding packets from socket: %s', data)
        buf = bitarray()  
        r = data.recv(1024)
        b = bitarray()
        b.frombytes(r)
        while len(r):
            buf.frombytes(r)
            logger.debug('chunking buffer of length %d bytes', len(buf)/8)
            i = 0
            while i < len(buf):
                if len(buf) < 2: break
                size = (int(buf[i:i+2].to01(), 2) + 1) * 24
                if len(buf) < (size * 8): break
                try:
                    packet = Packet.frombits(buf, i=i, check_crc=check_crc)
                    yield packet
                    i += (size * 8)
                except IncompletePacketError: break
                except (InvalidCrcError, ice):
                    if error_callback: error_callback(ice) 
                    if resync: i += 8
                    else: i += (size * 8)
            buf = buf[i:]
            logger.debug('reading from socket')
            r = data.recv(1024)
            logger.debug('read %d bytes from socket', len(r))            
    else:
        raise ValueError('unknown object to decode from: %s' % type(data))
    logger.debug('finished')
    return
