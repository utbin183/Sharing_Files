# server.py
# Centralized Index Server for P2P File Sharing

import socket
import threading

# Server configuration
SERVER_HOST = '0.0.0.0'
SERVER_PORT = 9000
BUFFER_SIZE = 1024

# Global data structures to track clients and files
# file_index maps: file_name -> set of (ip, port) tuples
file_index = {}
# client_lock is a mutex to protect access to the file_index
client_lock = threading.Lock()

def handle_client_connection(client_socket, client_address):
    """
    Handles an individual client connection in a separate thread.
    """
    print(f"[NEW CONNECTION] {client_address} connected.")
    
    try:
        while True:
            # Receive message from client
            message = client_socket.recv(BUFFER_SIZE).decode('utf-8')
            if not message:
                break # Client disconnected
                
            print(f"[REQUEST] Received from {client_address}: {message}")
            parts = message.split()
            command = parts[0].upper()

            if command == 'PUBLISH' and len(parts) == 3:
                # Client wants to publish a file
                # Format: PUBLISH <file_name> <peer_port>
                file_name = parts[1]
                peer_port = int(parts[2])
                peer_address = (client_address[0], peer_port) # Use client's IP
                
                # Use lock to safely modify the shared file_index
                with client_lock:
                    if file_name not in file_index:
                        file_index[file_name] = set()
                    file_index[file_name].add(peer_address)
                
                print(f"[PUBLISH] Peer {peer_address} added file: {file_name}")
                client_socket.sendall(b'PUBLISH_OK')

            elif command == 'FETCH' and len(parts) == 2:
                # Client wants to fetch a file
                # Format: FETCH <file_name>
                file_name = parts[1]
                
                # Find peers that have the file
                peer_list = []
                with client_lock:
                    if file_name in file_index:
                        peer_list = list(file_index[file_name])
                
                if not peer_list:
                    # No peers found
                    print(f"[FETCH] File not found: {file_name}")
                    client_socket.sendall(b'FETCH_NOT_FOUND')
                else:
                    # Send the list of peers back to the client
                    # Format: PEERS <ip1:port1> <ip2:port2> ...
                    response = 'PEERS ' + ' '.join([f"{ip}:{port}" for ip, port in peer_list])
                    print(f"[FETCH] Sending peers for {file_name}: {response}")
                    client_socket.sendall(response.encode('utf-8'))
            
            else:
                # Unknown command
                client_socket.sendall(b'UNKNOWN_COMMAND')

    except ConnectionResetError:
        print(f"[DISCONNECTED] Client {client_address} disconnected abruptly.")
    except Exception as e:
        print(f"[ERROR] Error handling client {client_address}: {e}")
    finally:
        # TODO: Implement logic to remove client's files from index on disconnect
        # This is complex, as the client might just be temporarily offline.
        # A 'ping' or 'heartbeat' mechanism is often needed.
        print(f"[CLOSED] Connection from {client_address} closed.")
        client_socket.close()

def run_server():
    """
    Main server function to listen for and accept new connections.
    """
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((SERVER_HOST, SERVER_PORT))
    server_socket.listen(5)
    print(f"[LISTENING] Server is listening on {SERVER_HOST}:{SERVER_PORT}")

    try:
        while True:
            # Accept a new connection
            client_socket, client_address = server_socket.accept()
            
            # Create a new thread to handle this client
            # This allows the server to handle multiple clients concurrently
            client_thread = threading.Thread(
                target=handle_client_connection,
                args=(client_socket, client_address)
            )
            client_thread.daemon = True # Allows server to exit even if threads are running
            client_thread.start()
            
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Server is shutting down.")
    finally:
        server_socket.close()

if __name__ == "__main__":
    run_server()