from utils import UDPPacket                                                                                                                           
import socket

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)                                                                                               
sock.connect(('127.0.0.1', 10000))                                                                                                                    
x = UDPPacket.create_syn()                                                                                                                            
sock.send(x.to_bytes())
