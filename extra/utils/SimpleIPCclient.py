import socket
import sys

# Create a UDS socket
sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

# Connect the socket to the port where the server is listening
server_address = '/tmp/mpvsocket'
print >>sys.stderr, 'connecting to %s' % server_address
try:
    sock.connect(server_address)
except socket.error, msg:
    print >>sys.stderr, msg
    sys.exit(1)
    
try:
    
    # Send data
    message = 'This is the message.  It will be repeated.'
    sock.sendall(message)

    amount_received = 0
    amount_expected = len(message)
    
    # Receive
    while True:
        data = sock.recv(1024)
        amount_received += len(data)
        print >>sys.stderr, 'received "%s"' % data

finally:
    print >>sys.stderr, 'closing socket'
    sock.close()
