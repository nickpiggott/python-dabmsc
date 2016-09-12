python-msc
==========

Python API for DAB MSC data as per ETSI TS 300 401, implementing datagroup and packet encoding and decoding.

# Dependencies

* python-mot

# Utilities

## decode

Debug utility for decoding MSC datagroup or packet bitstreams, optionally containing MOT objects.

Will read from stdin by default, but can also read from a file.

```
usage: decode [-h] [-o] [-d] [-p] [-c] [-m MODULES] [-X] [-f OUTPUT]
              [filename]

Decode and display datagroup or packet bitstreams

positional arguments:
  filename    Read bitstream from named file

optional arguments:
  -h, --help  show this help message and exit
  -o          decode objects
  -d          decode datagroups
  -p          decode packets
  -c          check CRCs
  -m MODULES  additional module to load
  -X          turn debug on
  -f OUTPUT   outfile file directory
```

Decode flags (`-o`, `-d`, `-c`) are defined for decoding different bitstream types in a nested fashion. The order of the specified specify the order of decoding, first to last.

For example, decoding a bitstream from a file containing MOT objects encoded as MSC datagroups, we would need to first decode the MSC datagroup and then the MOT object:

```
$ decode -f bitstream.dat -d -o
```

If we have an MOT object bitstream, encoded to MSC datagroups and then to MSC packets, but we wish only to decode down to MSC datagroups we would use the following:

```
$ decode -f bitstream.dat -p -d
```

By default, the CRC checksums of MSC packets and datagroups are checked. If the check fails, the packet or datagroup is not passed to the next decoding stage. When decoding to MOT objects this may result in an entire object being non-decodable (depending on packet or datagroup repetitions).

By default, only Core MOT Header and Directory Parameters are decoded when dealing with MOT objects. In order to decode and print additional parameters, the relevant module can be installed to the decoder using the `-m` option. This should specify the python packaget that contains the relevant registration to the HeaderParameter decode. For example, the `python-msc-spi` library registers the following:

```
HeaderParameter.decoders[0x25] = ScopeStart.decode_data
HeaderParameter.decoders[0x26] = ScopeEnd.decode_data
HeaderParameter.decoders[0x27] = ScopeId.decode_data
```

To register decoders for *ScopeStart*, *ScopeEnd* and *ScopeId* respectively. These parameters will then be outputted for relevant bitstreams in MOT decoding mode.


# Examples

Encoding a dummy (1k of zeroed data) image MOT object (using python-mot) to MSC datagroups. Prints the encoded datagroups out to the console.

```python
from mot import MotObject, ContentType
from msc.datagroups import *

# create MOT object
object = MotObject("TestObject", "\x00" * 1024, ContentType.IMAGE_JFIF)

# encode object
print 'encoding object'
datagroups = encode_headermode([object], segment_size=8181-2)

for datagroup in datagroups:
    print datagroup.tobytes(),
```

Decoding datagroups from stdin

```python
import sys
from dabdata.datagroups import *

f = sys.stdin
for d in decode_datagroups(f):
    print d
```

Encodes an MOT directory containing multiple dummy image MOT objects to MSC packets. Prints the encoded packets out to the console.

## packets

Encoding a set of datagroups from a placeholder image MOT object (using python-mot). Prints the encoded datagroups out to the console.

```python
from dabdata.mot import MotObject, ContentType
from dabdata.datagroups import *
from dabdata.packets import *

# create MOT object
object = MotObject("TestObject", "\x00" * 1024, ContentType.IMAGE_JFIF)

# encode object
print 'encoding object'
datagroups = encode_headermode([object], segment_size=8181-2)
packets = encode_packets(datagroups, 1, Packet.SIZE_96)

for packet in packets:
    print packet.tobytes(),
```

Decoding packets from stdin

```python
import sys
from dabdata.datagroups import *
from dabdata.packets import *

f = sys.stdin
for p in decode_packets(decode_datagroups(f)):
    print p
```

# TODO

* Add 0MQ transport

