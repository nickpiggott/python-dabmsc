from msc import bitarray_to_hex, int_to_bitarray, calculate_crc, InvalidCrcError, generate_transport_id
from mot import DirectoryEncoder, SortedHeaderInformation
from bitarray import bitarray
import logging
import types
import itertools

logger = logging.getLogger('msc.datagroups')

MAX_SEGMENT_SIZE=8189 # maximum data segment size in bytes

# datagroup types
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
                
def _segment(data, strategy):

    segments = []
        
    # partition the segments up using the maximum segment size
    i = 0
    if not data: return segments
    while i < len(data):
        segment_size = strategy.get_next_segment_size(data, i, segments)
        
        # get segment data
        segment_data = data[i:i+segment_size if i+segment_size < len(data) else len(data)]
                
        # segment header
        bits = bitarray()
        bits += int_to_bitarray(0, 3) # (0-2): Repetition Count remaining (0 = only broadcast)
        bits += int_to_bitarray(len(segment_data), 13) # (3-16): SegmentSize

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
        bits += int_to_bitarray(len(body_data) if body_data else 0, 28) # (0-27): BodySize in bytes
        bits += int_to_bitarray(len(extension_bits) / 8 + 7, 13) # (28-40): HeaderSize in bytes (core=7 + extension)
        bits += int_to_bitarray(object.get_type().type, 6)  # (41-46): ContentType 
        bits += int_to_bitarray(object.get_type().subtype, 9) # (47-55): ContentSubType
        bits += extension_bits # (56-n): Header extension data
        header_segments = _segment(bits.tobytes(), segmenting_strategy)

        # add header datagroups
        for i, segment in enumerate(header_segments):
            header_group = Datagroup(object.get_transport_id(), HEADER, segment, i, i%16, last=True if i == len(header_segments) - 1 else False)
            datagroups.append(header_group)
        
        # add body datagroups
        for i, segment in enumerate(body_segments):
            body_group = Datagroup(object.get_transport_id(), BODY, segment, i, i%16, last=True if i == len(body_segments) - 1 else False)
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
        entries += int_to_bitarray(object.get_transport_id(), 16)
        
        # add the core parameters into the header    
        entries += int_to_bitarray(len(object.get_body()), 28) # (0-27): BodySize in bytes
        entries += int_to_bitarray(len(extension_bits) / 8 + 7, 13) # (28-40): HeaderSize in bytes (core=7 + extension)
        entries += int_to_bitarray(object.get_type().type, 6)  # (41-46): ContentType 
        entries += int_to_bitarray(object.get_type().subtype, 9) # (47-55): ContentSubType
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
    bits += int_to_bitarray(len(entries.tobytes()) + 13 + len(directory_params.tobytes()), 30) # (2-31): DirectorySize: total size of the MOT directory in bytes, including the 13 header bytes and length of the directory parameter bytes
    bits += int_to_bitarray(len(objects), 16) # (32-47): NumberOfObjects: Total number of objects described by the directory
    bits += int_to_bitarray(0, 24) # (48-71): DataCarouselPeriod: Max time in tenths of seconds for the data carousel to complete a cycle. Value of zero for undefined
    bits += bitarray('000') # (72-74): RFU
    bits += int_to_bitarray(0, 13) # (75-87): SegmentSize: Size in bytes that will be used for the segmentation of objects within the MOT carousel. Value of zero indicates that objects can have different segmentation sizes. The last segment of an obect may be smaller than this size.
    bits += int_to_bitarray(len(directory_params.tobytes()), 16) # (88-103): DirectoryExtensionLength: Length of following directory extension bytes
    
    # add directory parameters
    bits += directory_params
    
    # add directory entries
    bits += entries 
    
    # segment and add directory datagroups with a new transport ID
    continuity_directory = 0
    directory_transport_id = generate_transport_id()
    segments = _segment(bits.tobytes(), segmenting_strategy)
    for i, segment in enumerate(segments):
        header_group = Datagroup(directory_transport_id, DIRECTORY_UNCOMPRESSED, segment, i, continuity_directory, last=True if i == len(segments) - 1 else False)
        tmp = bitarray()
        tmp.frombytes(header_group.tobytes())
        tmp.frombytes(header_group.tobytes())
        datagroups.append(header_group)
        continuity_directory = (continuity_directory + 1) % 16
        
    # add body datagroups
    continuity_body = 0
    for object in objects:
        segments = _segment(object.get_body(), segmenting_strategy)
        for i, segment in enumerate(segments):
            body_group = Datagroup(object.get_transport_id(), BODY, segment, i, continuity_body, last=True if i == len(segments) - 1 else False)
            datagroups.append(body_group)
            continuity_body = (continuity_body + 1) % 16
    # add empty body datagroups to assure continuity
    if continuity_body != 0:
        # segment header
        bits = bitarray()
        bits += int_to_bitarray(0, 3) # (0-2): Repetition Count remaining (0 = only broadcast)
        bits += int_to_bitarray(0, 13) # (3-16): SegmentSize
        dummysegment = bits.tobytes()
        body_group = Datagroup(generate_transport_id(), BODY, dummysegment, 0, continuity_body, last=True)
        datagroups.append(body_group)
        continuity_body = (continuity_body + 1) % 16
        if continuity_body != 0:
            continuity_body = 15
            body_group = Datagroup(generate_transport_id(), BODY, dummysegment, 0, continuity_body, last=True)
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

def decode_datagroups(data, error_callback=None, check_crc=True, resync=True):
    """
    Generator function to decode datagroups from a bitstream

    The bitstream may be presented as either a bitarray, a file object or a generator
    """ 

    if isinstance(data, bitarray):
        i = 0
        while i < len(data):
            datagroup = Datagroup.frombits(data, i=i, check_crc=check_crc)
            yield datagroup
            i += (datagroup.size * 8)
    elif isinstance(data, file):
        logger.debug('decoding datagroups from file: %s', data)
        buf = bitarray()
        reading = True
        while reading:
            try:
                r = data.read(8)
                buf.frombytes(r)
            except: 
                reading = False
                logger.exception("error")
            if not len(buf): 
                logger.debug('buffer is at zero length')
                return
            i = 0
            #logger.debug('chunking buffer of length %d bytes', len(buf)/8)
            length = len(buf)/8
            if length < 9: 
                continue
            size = int(buf[59:72].to01(), 2)
            if length < size: 
                #logger.debug('buffer still not at right size for datagroup size of %d bytes', size)
                continue
            while i < len(buf):
                try:
                    datagroup = Datagroup.frombits(buf, i=i, check_crc=check_crc)
                    yield datagroup
                    i = (datagroup.size * 8)
                    buf = buf[i:]
                except IncompleteDatagroupError: 
                    break
                except (InvalidCrcError, ice):
                    if error_callback: error_callback(ice) 
                    buf = buf[8:] # attempt to resync?
                    #i += 8
            
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
                except (IncompleteDatagroupError, ide): 
                    if error_callback: error_callback(ide) 
                except (InvalidCrcError, ice):
                    if error_callback: error_callback(ice) 
                del buf
                buf = bitarray()
                in_packet = False

class IncompleteDatagroupError(Exception):
    pass

class PaddingDatagroup:

    def __init__(self, delay=0):
        self.delay = delay

class Datagroup:
        
    def __init__(self, transport_id, type, data, segment_index, continuity, crc_enabled=True, repetition=0, last=False):
        self._transport_id = transport_id
        self._type = type
        self._data = data
        self.crc_enabled = crc_enabled
        self.continuity = continuity 
        self.repetition = repetition
        self.segment_index = segment_index
        self.last = last
        self.size = 7 + 2 + len(self._data) + 2 # encoded datagroup size for chunking = [dg header] + [segment header] + [data] + [crc]
        
    def __eq__(self, other):    
        if not isinstance(other, Datagroup): return False
        return self.get_transport_id() == other.get_transport_id() and self.get_type() == other.get_type() and self.segment_index == other.segment_index
        
    def get_transport_id(self):
        return self._transport_id
    
    def get_type(self):
        return self._type
    
    def get_data(self):
        return self._data
    
    def tobytes(self):
        
        bits = bitarray()
        
        # datagroup header
        bits += bitarray('0') # (0): ExtensionFlag - 0=no extension
        bits += bitarray('1' if self.crc_enabled else '0') # (1): CrcFlag - true if there is a CRC at the end of the datagroup
        bits += bitarray('1') # (2): SegmentFlag - 1=segment header included
        bits += bitarray('1') # (3): UserAccessFlag - true
        bits += int_to_bitarray(self._type, 4) # (4-7): DataGroupType
        bits += int_to_bitarray(self.continuity % 16, 4) # (8-11): ContinuityIndex
        bits += int_to_bitarray(self.repetition, 4) # (12-15): RepetitionIndex - remaining = 0 (only this once)
        
        # session header
        # segment field
        bits += bitarray('1' if self.last else '0') # (16): Last - true if the last segment
        bits += int_to_bitarray(self.segment_index, 15) # (17-32): SegmentNumber
        
        # user access field
        bits += bitarray('000') # (33-35): RFA
        bits += bitarray('1') # (36): TransportId - true to include Transport ID
        bits += int_to_bitarray(2, 4) # (37-40): LengthIndicator - length of transport Id and End user address fields (will be 2 bytes as only transport ID defined)
        bits += int_to_bitarray(self._transport_id, 16) # (41-56) transport ID

        # data field
        tmp = bitarray()
        tmp.frombytes(self._data)
        bits += tmp
        
        # CRC
        crc = 0;
        if self.crc_enabled: crc = calculate_crc(bits.tobytes())
        bits += int_to_bitarray(crc, 16)

        return bits.tobytes()
    
    @staticmethod
    def frombits(bits, i=0, check_crc=True):
        """Parse a datagroup from a bitarray, with an optional offset"""
       
        # check we have enough header first
        if (len(bits) - i) < ((9 + 2) * 8): raise IncompleteDatagroupError
       
        # datagroup header
        type = int(bits[4:8].to01(), 2)
        continuity = int(bits[8:12].to01(), 2)
        repetition = int(bits[12:16].to01(), 2)
                
        # session header
        # segment field
        last = bits[16]
        segment_index = int(bits[17:32].to01(), 2)
        
        # user access field
        transport_id = int(bits[40:56].to01(), 2)

        # data segment header
        size = int(bits[59:72].to01(), 2) # get size to check we have a complete datagroup
        if len(bits) < 72 + size * 8 + 16: raise IncompleteDatagroupError
        data = bits[72 : 72 + (size*8)]
        if check_crc:
            crc = int(bits[72 + len(data) : 72 + len(data) + 16].to01(), 2)
            calculated = calculate_crc(bits[:72+len(data)].tobytes())
            if crc != calculated: raise InvalidCrcError(crc, bits[:72+len(data) + 16].tobytes())  
        
        datagroup = Datagroup(transport_id, type, data.tobytes(), segment_index, continuity, True, repetition, last)
        logger.debug('parsed datagroup: %s', datagroup)
        
        return datagroup
    
    def __str__(self):
        if self._type == 3: type_description = 'MOT Header'
        elif self._type == 4: type_description = 'MOT Body'
        elif self._type == 6: type_description = 'MOT Directory (uncompressed)'
        elif self._type == 7: type_description = 'MOT Directory (compressed)'
        else: type_description = 'unknown'
        return '[segment=%d bytes], type=%d [%s], transportid=%d, segmentindex=%d, continuity=%d, last=%s' % (len(self._data), self._type, type_description, self._transport_id, self.segment_index, self.continuity, self.last)
        
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
