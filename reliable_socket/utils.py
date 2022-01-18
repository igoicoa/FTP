import struct
import time


def chunked(source, size):
    for i in range(0, len(source), size):
        yield source[i:i+size]


class UDPPacket:
    HEADER_SIZE = 12

    def __init__(self, seq_n, ack_n, flags, payload=None):
        self.seq_n = seq_n
        self.ack_n = ack_n
        self.flags = flags
        self.payload = payload if payload else b''
        self.time = time.time()

    def __eq__(self, other):
        return (self.seq_n == other.seq_n and
               self.ack_n == other.ack_n and
               self.flags == other.flags and
               self.payload == other.payload)

    def __repr__(self):
        return str(self.__dict__)

    def __str__(self):
        return str(self.__dict__)

    def __lt__(self, other):
        return self.seq_n < other.seq_n

    def __gt__(self, other):
        return self.seq_n > other.seq_n

    @staticmethod
    def flags_to_int(syn=False, ack=False, fin=False, psh=False):
        """
        Returns an integer representing the combination of flags
        """
        flag_list = [syn, ack, fin, psh]
        binarray = ''.join(map(str, map(int, flag_list)))
        return int(binarray, 2)

    @staticmethod
    def flag_from_int(flag_int):
        flag_list = list(map(bool, map(int, f'{flag_int:04b}')))
        flags = {
            'syn': flag_list[0],
            'ack': flag_list[1],
            'fin': flag_list[2],
            'psh': flag_list[3]
        }
        return flags

    @classmethod
    def create_package(cls, seq_n, ack_n, payload=None):
        return cls(seq_n, ack_n, None, payload)

    @classmethod
    def flag_dict(cls, syn=False, ack=False, fin=False, psh=False):
        return {
            'syn': syn,
            'ack': ack,
            'psh': psh,
            'fin': fin,
        }

    @classmethod
    def create_syn(cls):
        flags = cls.flag_dict(syn=True)
        return cls(0, 0, flags)

    @classmethod
    def create_synack(cls):
        """
        By convention all SYNs are seq_n 0. Thus all ack_n of a SYN+ACK should also be 0
        NOTE: Instead of using the ack_n as which should be the next byte, we are messaging
        which package number we are acking
        """
        flags = cls.flag_dict(syn=True, ack=True)
        return cls(0, 0, flags)

    @classmethod
    def create_ack(cls, seq_n, ack_n):
        flags = cls.flag_dict(ack=True)
        return cls(seq_n, ack_n, flags)

    @classmethod
    def create_data(cls, seq_n, ack_n, payload):
        flags = cls.flag_dict(ack=True, psh=True)
        return cls(seq_n, ack_n, flags, payload)

    @classmethod
    def create_fin(cls):
        flags = cls.flag_dict(fin=True)
        return cls(0, 0, flags)

    @classmethod
    def create_finack(cls):
        """
        By convention all SYNs are seq_n 0. Thus all ack_n of a SYN+ACK should also be 0
        NOTE: Instead of using the ack_n as which should be the next byte, we are messaging
        which package number we are acking
        """
        flags = cls.flag_dict(fin=True, ack=True)
        return cls(0, 0, flags)


    @property
    def flags_int(self):
        return self.flags_to_int(**self.flags)

    def to_bytes(self):
        pack = b''
        # First 4 bytes are the Sequence Number
        pack += struct.pack('I', self.seq_n)
        # 4 Bytes for Acknoledge Number
        pack += struct.pack('I', self.ack_n)
        # 4 Bytes to represent the Flags
        pack += struct.pack('I', self.flags_int)
        # The remaining bytes are data
        pack += self.payload

        return pack

    @classmethod
    def from_bytes(cls, byte_pack):
        seq_n = struct.unpack('I', byte_pack[0:4])[0]
        ack_n = struct.unpack('I', byte_pack[4:8])[0]
        flag_int = struct.unpack('I', byte_pack[8:12])[0]
        databytes = byte_pack[12:]

        flags = cls.flag_from_int(flag_int)

        return cls(seq_n, ack_n, flags, databytes)

    def tick(self):
        """
        Set the time to `now`. Intented to be used when sent in case the package was held for too
        long
        """
        self.time = time.time()

    def expired(self, rto=None):
        if not rto:
            return False

        return time.time() - self.time > rto

    def is_syn(self):
        return self.flags_int == 8

    def is_ack(self):
        return self.flags_int == 4

    def is_synack(self):
        return self.flags_int == 12

    def is_fin(self):
        return self.flags_int == 2

    def is_finack(self):
        return self.flags_int == 6

    def is_data(self):
        return self.flags_int == 5 and self.payload
