import unittest

from msc.datagroups import _segment, ConstantSegmentSize, CompletionTriggerSegmentingStrategy


class ConstantSegmentSizeTest(unittest.TestCase):

    def test_1(self):
        data = (" " * 1000).encode()
        segments = _segment(data, ConstantSegmentSize())
        assert len(segments) == 1
        assert len(segments[0]) == 1002
            
    def test_2(self):
        data = (" " * 16000).encode()
        segments = _segment(data, ConstantSegmentSize())
        assert len(segments) == 2     
        assert len(segments[0]) == 8191
        assert len(segments[1]) == 7813   
        
class CompletionTriggerSegmentingStrategyTest(unittest.TestCase):
    
    def test_1(self):
        data = (" " * 1000).encode()
        segments = _segment(data, CompletionTriggerSegmentingStrategy(64))
        total = 0
        for segment in segments: 
            total += len(segment)-2
        assert total == len(data)
        
    def test_2(self):
        data = (" " * 16000).encode()
        segments = _segment(data, CompletionTriggerSegmentingStrategy(64))
        total = 0
        for segment in segments: 
            total += len(segment)-2
        assert total == len(data)
        
    def test_3(self):
        data = (" " * 16000).encode()
        segments = _segment(data, CompletionTriggerSegmentingStrategy(64, maximum_segment_size=1024))
        total = 0
        for segment in segments: 
            total += len(segment)-2
        assert total == len(data)
             
    def test_4(self):
        data = (" " * 46).encode()
        segments = _segment(data, CompletionTriggerSegmentingStrategy(80, maximum_segment_size=1024))
        total = 0
        for segment in segments: 
            total += len(segment)-2
        assert total == len(data)  

if __name__ == "__main__":
    unittest.main()
