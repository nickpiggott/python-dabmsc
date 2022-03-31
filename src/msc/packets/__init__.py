from bitarray import bitarray
from bitarray.util import int2ba, ba2int
from msc import calculate_crc, InvalidCrcError
from msc.datagroups import Datagroup
from enum import Enum
from typing import List, Generator, Callable
from io import IOBase

import logging

logger = logging.getLogger('dabdata.packets')

class IncompletePacketError(Exception):
    pass

class PacketSize(Enum):
    SIZE_96 = 96
    SIZE_72 = 72
    SIZE_48 = 48
    SIZE_24 = 24

class Packet:
        
    def __init__(self, size : PacketSize, address : int, data : bytes, first : bool, last : bool, index : int):
        self.__size = size
        self.__address = address
        self.__data = data
        self.__first = first
        self.__last = last
        self.__index = index

    def get_size(self) -> PacketSize:
        return self.__size

    def get_address(self) -> int:
        return self.__address

    def get_data(self) -> bytes:
        return self.__data

    def is_first(self) -> bool:
        return self.__first

    def is_last(self) -> bool:
        return self.__last

    def get_index(self) -> int:
        return self.__index
        
    def tobytes(self) -> bytes:
        """
        Render the packet to its byte array representation
        """
        
        bits = bitarray()
        
        # build header
        bits += int2ba(int((self.__size.value / 24) - 1), 2) # (0-1): packet length
        bits += int2ba(self.__index, 2) # (2-3): continuity index
        bits += bitarray('1' if self.__first else '0') # (4): first packet of datagroup series
        bits += bitarray('1' if self.__last else '0') # (5): last packet of datagroup series
        bits += int2ba(self.__address, 10) # (6-15): packet address
        bits += bitarray('0') # (16): Command flag = 0 (data)
        bits += int2ba(len(self.__data), 7) # (17-23): useful data length

        # add the packet data
        tmp = bitarray()
        tmp.frombytes(self.__data)
        bits += tmp # (24-n): packet data
                    
        # add packet padding if needed
        bits += bitarray('0'*(self.__size.value - len(self.__data) - 5)*8)
        
        # add CRC
        bits += int2ba(calculate_crc(bits.tobytes()), 16)
        
        return bits.tobytes()

    @staticmethod
    def frombytes(data : bytes, check_crc : bool = True):
        """
        Parse a packet from a bitarray, with an optional offset
        """

        # check we have enough header first
        if (len(data) < (3)): 
            raise IncompletePacketError("the number of bytes existing %d is less than is required for a header (3 bytes)" % len(data))
       
        # take the next 9 bytes to examine the header
        bits = bitarray()
        bits.frombytes(data[:3])  

        size = PacketSize((ba2int(bits[0:2]) + 1) * 24)
        if(len(data) < size.value): raise IncompletePacketError('length of data is less than signalled data length %d bytes < %d bytes', len(data), size)

        index = ba2int(bits[2:4])
        first = bool(bits[4])
        last = bool(bits[5])
        address = ba2int(bits[6:16])
        data_length = ba2int(bits[17:24])
        payload = data[3:3+data_length]
        signalled = int.from_bytes(data[size.value - 2 : size.value], byteorder='big', signed=False)

        # check the CRC against a calculated one
        calculated = calculate_crc(data[:size.value - 2])
        if signalled != calculated: 
            raise InvalidCrcError(calculated, signalled)
        logger.debug('the signalled CRC %d matches the calculated CRC', signalled)
        
        packet = Packet(size=size, address=address, data=payload, first=first, last=last, index=index)
        logger.debug('parsed packet: %s', packet)
        
        return packet
        
    def __str__(self):
        return 'size=%d, address=%d, first=%s, last=%s, index=%d, data=%d bytes' % (self.__size.value, self.__address, self.__first, self.__last, self.__index, len(self.__data))
        
    def __repr__(self):
        return '<Packet: %s>' % str(self)

def encode_packets(datagroups : List[Datagroup], address : int = 1, size : PacketSize = PacketSize.SIZE_96, continuity=None) -> List[Packet]:

    """
    Encode a set of datagroups into packets
    """


    if not continuity: continuity = {}

    if address < 1 or address > 1024: raise ValueError('packet address must be greater than zero and less than 1024')
    
    packets = []
    
    def get_continuity_index(address) -> int:
        index=0
        if address in continuity:
            index = continuity[address]
            index += 1
            if index > 3: index = 0
        continuity[address] = index
        return index
    
    # encode the datagroups into a continuous datastream
    for datagroup in datagroups:
        data = datagroup.tobytes()
        chunk_size = size.value - 5
        for i in range(0, len(data), chunk_size):
            chunk = data[i:i+chunk_size if i+chunk_size < len(data) else len(data)]
            packet = Packet(size, address, chunk, True if i == 0 else False, True if i+chunk_size >= len(data) else False, get_continuity_index(address))
            packets.append(packet)
        
    return packets

def decode_packets(data, error_callback : Callable[[InvalidCrcError],None]=None, check_crc: bool=True, resync: bool=True) -> Generator[Packet, None, None]:

    """
    Generator function to decode packets from a bitstream

    The bitstream may be presented as either a bitarray, a file object or a socket
    """
       
    if isinstance(data, bytes):
        logger.debug('decoding packets from bytes')
        while len(data) >= PacketSize.SIZE_24.value: # minimum packet size
            size = (int((data[0] & 0b11000000) >> 6) + 1) * 24
            logger.debug("reading packet of size %d bytes", size)
            if len(data) < size:
                raise IncompletePacketError("packet size is greater than the available data, breaking")
            try:
                packet = Packet.frombytes(data[:size], check_crc=check_crc)
                yield packet
                data = data[size:]
            except InvalidCrcError as ice:
                if error_callback: error_callback(ice) 
                data = data[1:] # shuffle us forward a byte
    elif isinstance(data, IOBase):
        logger.debug('decoding packets from IO: %s', data)
        reading = True
        buf = bytes()
        while reading:
            try:
                buf += data.read()
            except: 
                reading = False
                logger.exception("error whilst reading from IO")
            if not len(buf): 
                logger.debug("IO buffer is now at zero length - breaking")
                return
            logger.debug('chunking buffer of length %d bytes', len(buf))
            length = len(buf)
            if length < 9: 
                continue
            bits = bitarray()
            bits.frombytes(buf[0:1])
            size = int(bits[0:2].to01(), 2) ##
            if len(buf) < size: break
            try:
                packet = Packet.frombytes(buf, check_crc=check_crc)
                yield packet
                buf = buf[size:]
            except IncompletePacketError: 
                break
            except InvalidCrcError as ice:
                if error_callback: error_callback(ice) 
                if resync: buf = buf[1:]
                else: buf = buf[size:]  
    else:
        raise ValueError('unknown object to decode from: %s' % type(data))
    logger.debug('finished')
    return
