import socket
import ssl

import h11_mypyc

################################################################
# Setup
################################################################

conn = h11_mypyc.Connection(our_role=h11_mypyc.CLIENT)
ctx = ssl.create_default_context()
sock = ctx.wrap_socket(socket.create_connection(("httpbin.org", 443)), server_hostname="httpbin.org")

################################################################
# Sending a request
################################################################


def send(event):
    print("Sending event:")
    print(event)
    print()
    # Pass the event through h11_mypyc's state machine and encoding machinery
    data = conn.send(event)
    # Send the resulting bytes on the wire
    sock.sendall(data)


send(
    h11_mypyc.Request(
        method="GET",
        target="/get",
        headers=[("Host", "httpbin.org"), ("Connection", "close")],
    )
)
send(h11_mypyc.EndOfMessage())

################################################################
# Receiving the response
################################################################


def next_event():
    while True:
        # Check if an event is already available
        event = conn.next_event()
        if event is h11_mypyc.NEED_DATA:
            # Nope, so fetch some data from the socket...
            data = sock.recv(2048)
            # ...and give it to h11_mypyc to convert back into events...
            conn.receive_data(data)
            # ...and then loop around to try again.
            continue
        return event


while True:
    event = next_event()
    print("Received event:")
    print(event)
    print()
    if type(event) is h11_mypyc.EndOfMessage:
        break

################################################################
# Clean up
################################################################

sock.close()
