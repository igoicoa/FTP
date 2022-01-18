from reliable_socket.utils import UDPPacket


def test_udp_comparators():
    x = UDPPacket(0, 0, None, None)
    y = UDPPacket(1, 0, None, None)

    assert x < y

    assert min([x, y]) == x
