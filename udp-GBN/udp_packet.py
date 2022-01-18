import random


class UDPPacket():

    def __init__(self, mode, filename, length, seq_number=random.randint(0, 100), data=''):
        self.length = length
        self.filename = filename
        self.sequence_number = seq_number
        self.mode = mode
        self.checksum = ''
        self.data = data
