from msc import calculate_crc, InvalidCrcError, generate_transport_id
from mot import DirectoryEncoder, SortedHeaderInformation
from bitarray import bitarray
from bitarray.util import int2ba, ba2int
import logging
import types
import itertools
from enum import Enum
from io import IOBase

logger = logging.getLogger('msc.datagroups')

MAX_SEGMENT_SIZE=8189 # maximum data segment size in bytes

# datagroup types
class DatagroupType(Enum):
    HEADER = 3
    BODY = 4
    DIRECTORY_UNCOMPRESSED = 6
    DIRECTORY_COMPRESSED = 7  

class SegmentingStrategy:
    
    def get_next_segment_size(self, data, position, segments):
        """Returns the suggested maximum size of the next segment"""
        raise NotImplementedError('strategy has not been implemented properly - expected method: get_next_segment_size(self, data, position, segments)')
    
class ConstantSegmentSize(SegmentingStrategy):
    """Strategy to ensure that each segment is the same size, apart
       from the last one, which may be smaller"""

    def __init__(self, maximum_segment_size=MAX_SEGMENT_SIZE):
        self.maximum_segment_size = maximum_segment_size
    
    def get_next_segment_size(self, data, position, segments):
        return self.maximum_segment_size

class CompletionTriggerSegmentingStrategy(SegmentingStrategy):
    """Strategy to ensure the last datagroup is small enough to be held within a single packet
       for triggering via the completion of the total set of datagroups.
       This is to enable synchronised imagery"""
       
    def __init__(self, target_final_segment_size, maximum_segment_size=MAX_SEGMENT_SIZE, ):
        if target_final_segment_size > maximum_segment_size: raise ValueError('target final segment size must be less than the maximum segment size')
        self.maximum_segment_size = maximum_segment_size
        
#        # calculate the estimated final segment size from parameters
#        estimated_final_segment_size = target_final_packet_size
#        estimated_final_segment_size -= 2 # packet CRC
#        estimated_final_segment_size -= 3 # packet header
#        estimated_final_segment_size -= 2 # datagroup CRC
#        estimated_final_segment_size -= 7 # datagroup header (typical minimal config)
        self.target_final_segment_size = target_final_segment_size
        
    def calculate_segment_sizes(self, length):
        
        # need to try for the exact target final segment size, or less
        # with equal sizes of the preceding segments - therefore they
        # will need to be exactly fitting
        X = self.maximum_segment_size
        Y = self.target_final_segment_size
        while Y > 0:
            while X > 0:
                if (length - Y + 2) % X == 0:
                    return X, Y
                X -= 1
            Y -= 1
            
    def get_next_segment_size(self, data, position, segments):            
            
        if not len(segments): # no calculation done yet
            X, Y = self.calculate_segment_sizes(len(data))
        else: 
            X = len(segments[0]) - 2
            n = 1
            Y = (len(data) / X) % n - 2
            while Y > self.target_final_segment_size:
                n += 1
                
        if len(data) - position > Y: return X
        else: return Y
                
def _segment(data : bytes, strategy : SegmentingStrategy):
    """
    Performs the actual segmenting, according to the segmentation strategy. Note
    that the incoming data must be a byte array.
    """

    segments = []
        
    # partition the segments up using the maximum segment size
    i = 0
    if not data: return segments
    if not type(data) == bytes: raise ValueError("Data to be segmented must be a byte array")
    while i < len(data):
        segment_size = strategy.get_next_segment_size(data, i, segments)
        
        # get segment data
        segment_data = data[i : i+segment_size if i+segment_size < len(data) else len(data)]
                
        # segment header
        bits = bitarray()
        bits += int2ba(0, 3) # (0-2): Repetition Count remaining (0 = only broadcast)
        bits += int2ba(len(segment_data), 13) # (3-16): SegmentSize

        segments.append((bits.tobytes()) + segment_data)
        
        i += segment_size

    return segments;    

def encode_headermode(objects, segmenting_strategy=None):
    """
    Encode a set of MOT Objects into header mode segments
    """

    datagroups = []
    if not segmenting_strategy: segmenting_strategy=ConstantSegmentSize()
    
    # backward compatibility
    if not isinstance(objects, list): objects = [objects] 
    logger.debug('encoding %d MOT objects to header mode datagroups', len(objects))

    for object in objects:   
        if not object: raise ValueError('object returned is null')

        # split body data into segments
        body_data = object.get_body()
        body_segments = _segment(body_data, segmenting_strategy)
    
        # encode header extension parameters
        extension_bits = bitarray()
        for parameter in object.get_parameters():
            extension_bits += parameter.encode()
        
        # insert the core parameters into the header    
        bits = bitarray()
        bits += int2ba(len(body_data) if body_data else 0, 28) # (0-27): BodySize in bytes
        bits += int2ba(int(len(extension_bits) / 8 + 7), 13) # (28-40): HeaderSize in bytes (core=7 + extension)
        bits += int2ba(object.get_contenttype().type, 6)  # (41-46): ContentType 
        bits += int2ba(object.get_contenttype().subtype, 9) # (47-55): ContentSubType
        bits += extension_bits # (56-n): Header extension data
        header_segments = _segment(bits.tobytes(), segmenting_strategy)

        # add header datagroups
        for i, segment in enumerate(header_segments):
            header_group = Datagroup(object.get_transport_id(), DatagroupType.HEADER, segment, i, i%16, last=True if i == len(header_segments) - 1 else False)
            datagroups.append(header_group)
        
        # add body datagroups
        for i, segment in enumerate(body_segments):
            body_group = Datagroup(object.get_transport_id(), DatagroupType.BODY, segment, i, i%16, last=True if i == len(body_segments) - 1 else False)
            datagroups.append(body_group)
        
        return datagroups;


def encode_directorymode(objects, directory_parameters=None, segmenting_strategy=None):
    """
    Encode a set of MOT objects into directory mode segments, along with a segmented
    directory object
    """

    datagroups = []
    if not segmenting_strategy: segmenting_strategy=ConstantSegmentSize()

    # build the directory entries
    entries = bitarray()
    for object in objects:              
        # encode header extension parameters
        extension_bits = bitarray()
        for parameter in object.get_parameters():
            extension_bits += parameter.encode()
        
        # transport ID in first 2 bytes
        entries += int2ba(object.get_transport_id(), 16)
        
        # add the core parameters into the header    
        entries += int2ba(len(object.get_body()), 28) # (0-27): BodySize in bytes
        entries += int2ba(int(len(extension_bits) / 8 + 7), 13) # (28-40): HeaderSize in bytes (core=7 + extension)
        entries += int2ba(object.get_contenttype().type, 6)  # (41-46): ContentType 
        entries += int2ba(object.get_contenttype().subtype, 9) # (47-55): ContentSubType
        entries += extension_bits # (56-n): Header extension data

    # build directory parameters
    directory_params = bitarray()
    if directory_parameters is not None:
        for parameter in directory_parameters:
            directory_params += parameter.encode()
    
    # build directory header
    bits = bitarray()
    bits += bitarray('0') # (0): CompressionFlag: This bit shall be set to 0
    bits += bitarray('0') # (1): RFU
    bits += int2ba(len(entries.tobytes()) + 13 + len(directory_params.tobytes()), 30) # (2-31): DirectorySize: total size of the MOT directory in bytes, including the 13 header bytes and length of the directory parameter bytes
    bits += int2ba(len(objects), 16) # (32-47): NumberOfObjects: Total number of objects described by the directory
    bits += int2ba(0, 24) # (48-71): DataCarouselPeriod: Max time in tenths of seconds for the data carousel to complete a cycle. Value of zero for undefined
    bits += bitarray('000') # (72-74): RFU
    bits += int2ba(0, 13) # (75-87): SegmentSize: Size in bytes that will be used for the segmentation of objects within the MOT carousel. Value of zero indicates that objects can have different segmentation sizes. The last segment of an obect may be smaller than this size.
    bits += int2ba(len(directory_params.tobytes()), 16) # (88-103): DirectoryExtensionLength: Length of following directory extension bytes
    
    # add directory parameters
    bits += directory_params
    
    # add directory entries
    bits += entries 
    
    # segment and add directory datagroups with a new transport ID
    directory_transport_id = generate_transport_id()
    segments = _segment(bits.tobytes(), segmenting_strategy)
    for i, segment in enumerate(segments):
        header_group = Datagroup(directory_transport_id, DatagroupType.DIRECTORY_UNCOMPRESSED, segment, i, i%16, last=True if i == len(segments) - 1 else False)
        datagroups.append(header_group)
        
    # add body datagroups
    for object in objects:
        segments = _segment(object.get_body(), segmenting_strategy)
        for i, segment in enumerate(segments):
            body_group = Datagroup(object.get_transport_id(), DatagroupType.BODY, segment, i, i%16, last=True if i == len(segments) - 1 else False)
            datagroups.append(body_group)
    return datagroups

import select
def read(fd, n = 1):
    poll = select.poll()
    poll.register(fd.fileno(), select.POLLIN or select.POLLPRI)
    p = poll.poll()
    if len(p):
        f = p[0]
        if f[1] > 0:
            return fd.read(n)

def decode_datagroups(data : bytes, error_callback=None, check_crc=True, resync=True):
    """
    Generator function to decode datagroups from a bitstream

    The bitstream may be presented as either a byte array, a file object or a generator
    """ 

    if isinstance(data, bytes):
        logger.debug("decoding datagroups from a byte array of length %d" % len(data))
        while len(data):
            datagroup = Datagroup.frombytes(data, check_crc=check_crc)
            datagroup_length = datagroup.get_size()
            yield datagroup
            logger.debug("moving forward %d bytes", datagroup_length)
            data = data[datagroup_length:]
    elif isinstance(data, IOBase):
        logger.debug('decoding datagroups from IO: %s', data)
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
            bits.frombytes(buf[0:9])
            size = int(bits[59:72].to01(), 2) ##
            if length < size: 
                logger.debug('buffer still not at right size for datagroup size of %d bytes', size)
                continue
            while len(buf):
                try:
                    datagroup = Datagroup.frombytes(buf, check_crc=check_crc)
                    yield datagroup
                    buf = buf[datagroup.get_size():]
                except IncompleteDatagroupError: 
                    logger.warning('encountered an incomplete datagroup')
                    break
                except InvalidCrcError as ice:
                    logger.warning('encountered an invalid CRC')
                    if error_callback: error_callback(ice) 
                    buf = buf[1:] # attempt to resync?
            
    elif isinstance(data, types.GeneratorType):
        logger.debug('decoding datagroups from generator: %s', data)
        buf = bitarray()
        
        i = 0
        in_packet = False
        for p in data:
            if not in_packet and p.first: 
                in_packet = True
            elif not in_packet: continue 
            
            buf.frombytes(p.data)
            
            if p.last:
                logger.debug('got packet %s -  buffer now %d bytes', p, len(buf)/8)
                try:
                    datagroup = Datagroup.frombits(buf, i=i, check_crc=check_crc)
                    logger.debug('yielding datagroup: %s', datagroup)
                    yield datagroup                    
                except IncompleteDatagroupError as ide: 
                    if error_callback: error_callback(ide) 
                except InvalidCrcError as ice:
                    if error_callback: error_callback(ice) 
                del buf
                buf = bitarray()
                in_packet = False
    else:
        raise ValueError("unknown type when decoding datagroups: %s" % type(data))

class IncompleteDatagroupError(Exception):
    pass

class PaddingDatagroup:

    def __init__(self, delay=0):
        self.delay = delay

class Datagroup:
        
    def __init__(self, transport_id : int, type : DatagroupType, data : bytes, segment_index : int, continuity : bool, repetition : int=0, last : bool=False):
        if transport_id > 65535 : raise ValueError('transport id must be no greater than 65535')
        self.__transport_id = transport_id
        self.__type = type
        self.__data = data
        self.__continuity = continuity 
        self.__repetition = repetition
        self.__segment_index = segment_index
        self.__last = last
        
    def __eq__(self, other):    
        if not isinstance(other, Datagroup): return False
        return self.get_transport_id() == other.get_transport_id() and self.get_type() == other.get_type() and self.segment_index == other.segment_index
        
    def get_transport_id(self) -> int:
        return self.__transport_id
    
    def get_type(self) -> DatagroupType:
        return self.__type
    
    def get_data(self) -> bytes:
        """
        Return the data carried by the datagroup
        """
        return self.__data

    def get_continuity(self) -> int:
        return self.__continuity

    def get_repetition(self) -> int:
        return self.__repetition

    def get_segment_index(self) -> int:
        return self.__segment_index

    def get_last(self) -> bool:
        return self.__last
    
    def get_size(self) -> int:
        return 7 + len(self.__data) + 2

    def tobytes(self) -> bytes:
        """
        Encode the datagroup into a byte array
        """
        logging.debug("encoding %s" % self)
        
        bits = bitarray()
        
        # datagroup header
        bits += bitarray('0') # (0): ExtensionFlag - 0=no extension
        bits += bitarray('1') # (1): CrcFlag - true if there is a CRC at the end of the datagroup
        bits += bitarray('1') # (2): SegmentFlag - 1=segment header included
        bits += bitarray('1') # (3): UserAccessFlag - true
        bits += int2ba(self.__type.value, 4) # (4-7): DataGroupType
        bits += int2ba(self.__continuity % 16, 4) # (8-11): ContinuityIndex
        bits += int2ba(self.__repetition, 4) # (12-15): RepetitionIndex - remaining = 0 (only this once)
        
        # session header
        # segment field
        bits += bitarray(1 if self.__last else 0) # (16): Last - true if the last segment
        bits += int2ba(self.__segment_index, 15) # (17-32): SegmentNumber
        
        # user access field
        bits += bitarray('000') # (33-35): RFA
        bits += bitarray('1') # (36): TransportId - true to include Transport ID
        bits += int2ba(2, 4) # (37-40): LengthIndicator - length of transport Id and End user address fields (will be 2 bytes as only transport ID defined)
        bits += int2ba(self.__transport_id, 16) # (41-56) transport ID

        # data field
        data = bits.tobytes()
        data += self.__data
        
        # validate CRC
        # 5.3.3.4 The data group CRC shall be a 16-bit CRC word calculated on the data group header, the session header and the data group data field.
        crc = calculate_crc(data)
        logger.debug('calculated CRC of %d on %d bytes: %s', crc, len(data), data.hex())
        data += int.to_bytes(crc, 2, 'big')

        logging.debug("encoded datagroup %s to %d bytes" % (self, len(data)))

        return data
     
    @staticmethod
    def frombytes(data : bytes, check_crc : bool=True):
        """
        Parse a datagroup from a byte array, with an optional offset
        """

        # check we have enough header first
        if (len(data) < (7 + 2)): 
            raise IncompleteDatagroupError("the number of bytes existing %d is less than is required for a header" % len(data))
       
        # take the next 9 bytes to examine the header
        bits = bitarray()
        bits.frombytes(data[:9])  

        # datagroup header - we assume: no extension, CRC, segment, no UA
        if bits[0]: raise ValueError("extension field set - not implemented")
        if not bits[1]: raise ValueError("CRC flag not set - not implemented")
        if not bits[2]: raise ValueError("segment field not set - not implemented")
        if not bits[3]: raise ValueError("user access field not set - not implemented")
        type = DatagroupType(ba2int(bits[4:8]))
        logger.debug("parsed datagroup type: %s", type)
        continuity = ba2int(bits[8:12])
        logger.debug("parsed continuity: %d", continuity)
        repetition = ba2int(bits[12:16])
        logger.debug("parsed repetition: %d", repetition)
                
        # session header
        # segment field
        last = bits[16]
        logger.debug("parsed last flag: %d", last)
        segment_index = ba2int(bits[17:32])
        logger.debug("parsed segment index: %d", segment_index)

        if not bits[35]: raise ValueError("transport id flag not set - not implemented")
        if ba2int(bits[36:40]) != 2: raise ValueError("length indicator different to 2 - not implemented")

        # user access field
        transport_id = ba2int(bits[40:56])
        logger.debug("parsed transport id: %d", transport_id)

        # data segment header
        size = ba2int(bits[59:72]) 

        # calculate if we have enough data for: offset + datagroup header (incl. segment header) + data + CRC
        if len(data) < (9 + size + 2): 
            raise IncompleteDatagroupError("the number of bytes is less than is required for the entire datagroup")
        logger.debug("reading a datagroup segment payload of %d bytes with a 2 byte header" % size)
        payload = data[7 : 7 + 2 + size]
        signalled = int.from_bytes(data[7 + len(payload) : 7 + len(payload) + 2], byteorder='big', signed=False)

        # check the CRC against a calculated one
        calculated = calculate_crc(data[:7+2+size])
        if signalled != calculated: 
            raise InvalidCrcError(calculated, signalled)
        logger.debug('the signalled CRC %d matches the calculated CRC', signalled)
        
        datagroup = Datagroup(transport_id, type, payload, segment_index=segment_index, continuity=continuity, repetition=repetition, last=last)
        logger.debug('parsed datagroup: %s', datagroup)
        
        return datagroup
    
    def __str__(self):
        return '[segment=%d bytes], type=%d [%s], transportid=%d, segmentindex=%d, continuity=%d, last=%s' % (len(self.__data), self.__type.value, self.__type.name, self.__transport_id, self.__segment_index, self.__continuity, self.__last)
        
    def __repr__(self):
        return '<DataGroup: %s>' % str(self)
    
class DirectoryDatagroupEncoder(DirectoryEncoder):

    def __init__(self, segmenting_strategy=None, single=False):
        DirectoryEncoder.__init__(self)
        self.segmenting_strategy = segmenting_strategy
        self.single = single
        self.datagroups = []
        self.regenerate()

    def add(self, object):
        if object in self.objects: return False
        self.objects.append(object)
        self.regenerate()
        return True

    def remove(self, object):
        if object not in self.objects: return False
        self.objects.remove(object)
        self.regenerate()
        return True

    def clear(self):
        self.objects = []
        self.regenerate()
        return True

    def set(self, objects):
        if objects == self.objects: return False
        self.objects = objects
        self.regenerate()
        return True

    def regenerate(self):
        """called when the directory needs to regenerate"""
        self.datagroups = encode_directorymode(self.objects, directory_parameters=[SortedHeaderInformation()], segmenting_strategy=self.segmenting_strategy) 
        if self.single: self.iterator = iter(self.datagroups)
        else: self.iterator = itertools.cycle(self.datagroups)

    def __iter__(self):
        return self.iterator

    def __next__(self):
        return next(self.iterator)
