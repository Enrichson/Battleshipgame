import socket
import threading
import pickle
import struct
import zlib
import random
from queue import Queue
from battleship import run_multi_player_game_online

HOST = '127.0.0.1'
PORT = 5000
game_running = False
spectators = []
player_queue = Queue()
unique_id_counter = 1
packet_count = 0
disconnected_players = {} 
active_players = {}  
spectators_lock = threading.Lock()

PACKET_TYPE_GAME = 1
PACKET_TYPE_CHAT = 2
PACKET_TYPE_SYSTEM = 3
PACKET_TYPE_SPECTATOR = 4
PACKET_TYPE_BOARD = 5
PACKET_TYPE_PROMPT = 6


def create_packet(sequence_number, packet_type, payload):
    """
    Create a packet with a custom header and checksum.
    """
    payload_bytes = payload.encode('utf-8')
    payload_length = len(payload_bytes)
    header = struct.pack('!H B I', sequence_number, packet_type, payload_length)
    checksum = zlib.crc32(header + payload_bytes)
    packet = header + struct.pack('!I', checksum) + payload_bytes
    #print(f"[DEBUG] Created Packet: Sequence={sequence_number}, Type={packet_type}, Length={payload_length}, Checksum={checksum}")
    return packet


def parse_packet(packet):
    """
    Parse a packet and verify its checksum.
    """
    try:
        header = packet[:7]  # First 7 bytes: Sequence Number (2), Packet Type (1), Payload Length (4)
        checksum = struct.unpack('!I', packet[7:11])[0]
        payload = packet[11:]

        # Recompute checksum
        computed_checksum = zlib.crc32(header + payload)
        if checksum != computed_checksum:
            raise ValueError("[ERROR]: Checksum mismatch, packet discarded.")

        sequence_number, packet_type, payload_length = struct.unpack('!H B I', header)
        #print(f"[DEBUG] Parsed Packet: Sequence={sequence_number}, Type={packet_type}, Length={payload_length}, Checksum={checksum}")
        return sequence_number, packet_type, payload.decode('utf-8')
    except Exception as e:
        print(f"[ERROR] Failed to parse packet: {e}")
        return None


def send_packet(conn, sequence_number, packet_type, payload):
    packet = create_packet(sequence_number, packet_type, payload)
    conn.sendall(packet)


def receive_packet(conn):
    try:
        # Read the header first (7 bytes for header + 4 bytes for checksum)
        header_and_checksum = b''
        while len(header_and_checksum) < 11:
            try:
                chunk = conn.recv(11 - len(header_and_checksum))
                if not chunk:
                    return None
                header_and_checksum += chunk
            except socket.timeout:
                print("[INFO] Timeout occurred while waiting for data (header).")
                return None

        # Extract payload length from the header
        _, _, payload_length = struct.unpack('!H B I', header_and_checksum[:7])

        # Read the payload (allow empty payload)
        payload = b''
        while len(payload) < payload_length:
            try:
                chunk = conn.recv(payload_length - len(payload))
                if not chunk:
                    break
                payload += chunk
            except socket.timeout:
                print("[INFO] Timeout occurred while waiting for data (payload).")
                return None

        # Combine header, checksum, and payload
        packet = header_and_checksum + payload
        return parse_packet(packet)
    except socket.timeout:
        print("[INFO] Timeout occurred while waiting for data (outer).")
        return None
    except Exception as e:
        print(f"[ERROR] Failed to receive packet: {e}")
        return None

def notify_and_disconnect_lobby():
    """
    Notify all clients in the lobby that the server is shutting down and disconnect them.
    """
    for conn, addr in spectators:
        try:
            send_packet(conn, 0, 1,
                        "Server is shutting down. Disconnecting...")
            conn.close()
            print(f"[INFO] Disconnected client {addr} from the lobby.")
        except Exception as e:
            print(f"[ERROR] Error while disconnecting client {addr}: {e}")
    spectators.clear()


def ask_spectators_to_play():
    """
    Notify spectators and ask if they want to play the next game.
    Returns a list of willing spectators.
    """
    willing_spectators = []
    with spectators_lock:
        for conn, addr in spectators:
            try:
                send_packet(conn, 0, 6,
                            "Do you want to play the next game? (y/n):")
                response = receive_packet(conn)
                if response and response[2].strip().lower() == 'y':
                    willing_spectators.append((conn, addr))
            except Exception as e:
                print(
                    f"[ERROR] Failed to communicate with spectator {addr}: {e}"
                )
                spectators.remove(
                    (conn, addr))  # Remove disconnected spectators
    return willing_spectators


def handle_lobby_connections(server_socket):
    global unique_id_counter, disconnected_players, spectators

    while True:
        try:
            conn, addr = server_socket.accept()
            print(f"[INFO] New client connected from {addr}.")
            send_packet(
                conn, 0, 1,
                "Welcome! Are you a new player, reconnecting, or a spectator? (Type 'new', your user ID, or 'spectator'):"
            )

            try:
                packet = receive_packet(conn)
                if not packet:
                    print("[ERROR] Failed to receive user input.")
                    conn.close()
                    continue

                _, _, user_input = packet

                if user_input.lower() == "new" or user_input.lower() == "n":
                    # Assign a new user ID
                    user_id = unique_id_counter
                    unique_id_counter += 1
                    player_queue.put((conn, addr, user_id))
                    send_packet(
                        conn, user_id, 3,
                        f"Welcome, Player {user_id}! You are in the queue. Waiting for another player..."
                    )
                    print(
                        f"[INFO] New player assigned ID {user_id} and added to the queue."
                    )

                elif user_input.isdigit() and int(
                        user_input) in disconnected_players:
                    # Handle reconnection
                    user_id = int(user_input)
                    game_state, _ = disconnected_players.pop(user_id)
                    send_packet(
                        conn, user_id, 3,
                        f"Welcome back, Player {user_id}! Reconnecting you to your game..."
                    )
                    print(f"[INFO] Player {user_id} reconnected.")
                    # Resume the game
                    threading.Thread(target=resume_game,
                                    args=(conn, user_id, server_socket,
                                        notify_spectators, send_packet,
                                        receive_packet, disconnected_players),
                                    daemon=True).start()

                elif user_input.lower() == "spectator" or user_input.lower(
                ) == "s":
                    # Add the client to the spectators list
                    with spectators_lock:
                        spectators.append((conn, addr))
                    send_packet(
                        conn, 0, 3,
                        "You are now spectating. You will receive updates about ongoing games."
                    )
                    print(f"[INFO] Client {addr} is now spectating.")
                    notify_spectators("A new spectator has joined.")

                else:
                    send_packet(
                        conn, 0, 3,
                        "Invalid input. Please type 'new', your user ID, or 'spectator'."
                    )
                    conn.close()

            except Exception as e:
                print(f"[ERROR] Error handling connection from {addr}: {e}")
                conn.close()
        except socket.timeout:
            continue

def notify_spectators(message, board1=None, board2=None):
    """
    Send a message to all spectators. Optionally include the updated game boards.
    """
    global spectators

    with spectators_lock:
        for conn, addr in spectators:
            try:
                send_packet(conn, 0, 4, message)
                if board1 and board2:
                    send_packet(conn, 0, 5, f"\nPlayer 1's Board:\n{board1}\n")
                    send_packet(conn, 0, 5, f"\nPlayer 2's Board:\n{board2}\n")
            except Exception as e:
                print(f"[ERROR] Failed to notify spectator {addr}: {e}")
                spectators.remove(
                    (conn, addr))  # Remove disconnected spectators


def wait_for_reconnection(server_socket, player_id, timeout=30):
    """
    Wait for a disconnected player to reconnect within the given timeout.
    Returns the new connection if the player reconnects, or None if the timeout expires.
    Resets the server socket timeout after use.
    """
    print(f"[INFO] Waiting for Player {player_id} to reconnect...")
    original_timeout = server_socket.gettimeout()
    server_socket.settimeout(timeout)
    try:
        conn, addr = server_socket.accept()
        print(f"[INFO] Connection from {addr} for reconnection. Prompting for user ID...")
        send_packet(conn, 0, 3, "Please enter your user ID to reconnect:")
        packet = receive_packet(conn)
        if not packet:
            print("[ERROR] No user ID received for reconnection.")
            conn.close()
            return None
        _, _, user_input = packet
        if user_input.isdigit() and int(user_input) == player_id:
            print(f"[INFO] Player {player_id} successfully reconnected from {addr}")
            return conn
        else:
            send_packet(conn, 0, 3, "Invalid user ID for reconnection. Disconnecting.")
            print(f"[ERROR] Invalid user ID {user_input} for reconnection attempt from {addr}")
            conn.close()
            return None
    except socket.timeout:
        print(f"[INFO] Player {player_id} did not reconnect within the timeout.")
        return None
    except Exception as e:
        print(f"[ERROR] An unexpected error occurred while waiting for Player {player_id}: {e}")
        return None
    finally:
        server_socket.settimeout(original_timeout)
        
    

def resume_game(conn, user_id, server_socket, notify_spectators, send_packet,
                receive_packet, disconnected_players):
    try:
        # Load the saved game state from the file
        game_state = load_game_state("game_state.pkl")
        if not game_state:
            raise ValueError("Failed to load game state from file.")

        # Retrieve the second player's connection
        user_id1 = game_state["user_id1"]
        user_id2 = game_state["user_id2"]
        
        if user_id == user_id1:
            # Player 1 is reconnecting
            conn1 = conn
            if user_id2 in disconnected_players:
                conn2 = disconnected_players[user_id2][1]
                print(
                    f"[INFO] Retrieved Player 2's connection from disconnected_players."
                )
            elif user_id2 in active_players:
                conn2 = active_players[user_id2]
                print(f"[INFO] Player 2 is still actively connected.")
            else:
                conn2 = None
        elif user_id == user_id2:
            # Player 2 is reconnecting
            conn2 = conn
            if user_id1 in disconnected_players:
                conn1 = disconnected_players[user_id1][1]
                print(
                    f"[INFO] Retrieved Player 1's connection from disconnected_players."
                )
            elif user_id1 in active_players:
                conn1 = active_players[user_id1]
                print(f"[INFO] Player 1 is still actively connected.")
            else:
                conn1 = None
        else:
            raise ValueError(
                f"Invalid user_id: {user_id}. It does not match Player 1 or Player 2."
            )

        # Validate connections
        if conn1 is None or conn2 is None:
            send_packet(
                conn, user_id, 3,
                "The other player has disconnected. The game cannot be resumed."
            )
            print(
                f"[ERROR] Cannot resume game: One of the players is disconnected."
            )
            return

        # Resume the game loop
        run_multi_player_game_online(conn1,
                                     conn2,
                                     notify_spectators,
                                     user_id1,
                                     user_id2,
                                     server_socket,
                                     wait_for_reconnection,
                                     send_packet,
                                     receive_packet,
                                     disconnected_players,
                                     active_players,
                                     resuming_game=True,
                                     saved_game_state=game_state)
    except Exception as e:
        print(f"[ERROR] Failed to resume game for Player {user_id}: {e}")
        send_packet(conn, user_id, 3,
                    "Failed to resume your game. Please try again later.")
        conn.close()


def save_game_state(filename, game_state):
    try:
        with open(filename, 'wb') as f:
            pickle.dump(game_state, f)
        print(f"[INFO] Game state saved to {filename}")
    except Exception as e:
        print(f"[ERROR] Failed to save game state: {e}")


def load_game_state(filename):
    try:
        with open(filename, 'rb') as f:
            game_state = pickle.load(f)
        print(f"[INFO] Game state loaded from {filename}")
        return game_state
    except Exception as e:
        print(f"[ERROR] Failed to load game state: {e}")
        return None

def simulate_packet_transmission_with_errors(error_rate):
    """
    Simulate packet transmission with artificial errors.
    Measure how many packets are flagged as corrupted.

    Args:
        total_packets (int): Total number of packets to simulate.
        error_rate (float): Probability of injecting an error into a packet (0.0 to 1.0).

    Returns:
        int: Number of corrupted packets detected.
    """
    corrupted_count = 0

    if packet_count == 0:
        print("[INFO] No packets were sent during gameplay. Skipping error simulation.")
        return corrupted_count

    for i in range(packet_count):
        sequence_number = i
        packet_type = 1 
        payload = f"Test payload {i}"
        packet = create_packet(sequence_number, packet_type, payload)

        if random.random() < error_rate:
            packet = bytearray(packet)
            corrupt_index = random.randint(0, len(packet) - 1)
            packet[corrupt_index] ^= 0xFF 
            packet = bytes(packet)

        if parse_packet(packet) is None:
            corrupted_count += 1

    print(f"\n[INFO] Statistical Summary: Simulated packet transmission completed.")
    print(f"Total Packets Sent During Gameplay: {packet_count}")
    print(f"Corrupted Packets Detected: {corrupted_count}")
    print(f"Error Rate: {error_rate * 100:.2f}%")
    if packet_count > 0:
        print(f"Detection Rate: {(corrupted_count / packet_count) * 100:.2f}%")
    return corrupted_count

def main():
    global game_running, unique_id_counter, player_queue, spectators

    print(f"[INFO] Server listening on {HOST}:{PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen(5)  # Allow up to 5 clients to connect
        print("[DEBUG] Waiting for players to connect...")

        # Start the lobby thread to handle extra players
        lobby_thread = threading.Thread(target=handle_lobby_connections,
                                        args=(s, ),
                                        daemon=True)
        lobby_thread.start()
        print("[INFO] Lobby thread started to handle extra clients.")

        try:
            while True:
                # Wait for two players to join the queue
                while player_queue.qsize() < 2:
                    print("[INFO] Waiting for two players to join...")
                    threading.Event().wait(1)  # Wait for players to join

                # Assign Player 1 and Player 2
                conn1, addr1, user_id1 = player_queue.get()
                print(
                    f"[INFO] Player 1 connected from {addr1} with ID {user_id1}"
                )
                conn2, addr2, user_id2 = player_queue.get()
                print(
                    f"[INFO] Player 2 connected from {addr2} with ID {user_id2}"
                )

                # Notify spectators that the game is starting
                notify_spectators(
                    f"Game is starting! Player 1 (ID {user_id1}) and Player 2 (ID {user_id2}) are ready to play.\n"
                )

                game_running = True  # Set the game running flag to True

                # Start the multiplayer game
                try:
                    run_multi_player_game_online(
                        conn1, conn2, notify_spectators, user_id1, user_id2, s,
                        wait_for_reconnection, send_packet, receive_packet,
                        disconnected_players, active_players)

                    # Ask players if they want to play again
                    while True:
                        try:
                            send_packet(conn1, user_id1, 6, "Do you want to play again? (y/n):")
                            send_packet(conn2, user_id2, 6, "Do you want to play again? (y/n):")

                            try:
                                conn1.settimeout(10)
                                response1 = receive_packet(conn1)
                            except socket.timeout:
                                print("[INFO] Player 1 did not respond to replay prompt in time.")
                                response1 = None

                            try:
                                conn2.settimeout(10)
                                response2 = receive_packet(conn2)
                            except socket.timeout:
                                print("[INFO] Player 2 did not respond to replay prompt in time.")
                                response2 = None

                            # Reset socket timeout to default (optional, if you use timeouts elsewhere)
                            conn1.settimeout(None)
                            conn2.settimeout(None)

                            valid_yes = ["y", "yes"]
                            valid_no = ["n", "no"]

                            def sanitize(resp, conn, user_id):
                                if not resp or resp[2].strip().lower() not in valid_yes + valid_no:
                                    send_packet(conn, user_id, 6, "Invalid input. Please enter 'y', 'yes', 'n', or 'no'.")
                                    return None
                                return resp[2].strip().lower()

                            resp1 = sanitize(response1, conn1, user_id1) if response1 is not None else None
                            resp2 = sanitize(response2, conn2, user_id2) if response2 is not None else None

                            # If a player did not respond (timeout), close their connection and treat as "no"
                            if response1 is None:
                                print(f"[INFO] Player 1 did not respond to replay prompt. Closing connection.")
                                try:
                                    conn1.close()
                                except Exception as e:
                                    print(f"[ERROR] Error while closing Player 1 connection: {e}")
                                resp1 = "no"

                            if response2 is None:
                                print(f"[INFO] Player 2 did not respond to replay prompt. Closing connection.")
                                try:
                                    conn2.close()
                                except Exception as e:
                                    print(f"[ERROR] Error while closing Player 2 connection: {e}")
                                resp2 = "no"

                            # Now, if either said no (or timed out), break out of the rematch loop
                            if resp1 not in valid_yes or resp2 not in valid_yes:
                                break  # End rematch loop, do not reprompt

                        except (BrokenPipeError, ConnectionResetError):
                            print("[ERROR] One of the players disconnected during the rematch prompt.")
                            notify_spectators("The game has ended due to a player disconnecting.\n")
                            break

                except Exception as e:
                    print(f"[ERROR] An error occurred during the game: {e}")
                    notify_spectators("The game has ended due to an error.\n")

                finally:
                    game_running = False
                    # Close connections for both players
                    try:
                        conn1.close()
                        print(f"[INFO] Player 1 (ID {user_id1}) connection closed.")
                    except Exception as e:
                        print(f"[ERROR] Error while closing Player 1 connection: {e}")

                    try:
                        conn2.close()
                        print(f"[INFO] Player 2 (ID {user_id2}) connection closed.")
                    except Exception as e:
                        print(f"[ERROR] Error while closing Player 2 connection: {e}")

                    error_rate = 0.5
                    simulate_packet_transmission_with_errors(error_rate)

                    # After the replay prompt loop ends, ask spectators if they want to play
                    willing_spectators = ask_spectators_to_play()
                    if len(willing_spectators) >= 2:
                        print("[INFO] Promoting willing spectators to players for the next game.")
                        # Remove from spectators and add to player queue
                        with spectators_lock:
                            for conn, addr in willing_spectators[:2]:
                                spectators.remove((conn, addr))
                        user_id_a = unique_id_counter
                        unique_id_counter += 1
                        user_id_b = unique_id_counter
                        unique_id_counter += 1
                        player_queue.put((willing_spectators[0][0], willing_spectators[0][1], user_id_a))
                        player_queue.put((willing_spectators[1][0], willing_spectators[1][1], user_id_b))
                    else:
                        print("[INFO] Not enough willing spectators to start the next game. Waiting for new players.")

                    # Now notify remaining spectators that the game is over
                    notify_spectators("The game has ended. Thank you for watching!")

        except KeyboardInterrupt:
            print("[INFO] Server shutting down due to KeyboardInterrupt.")
        finally:
            notify_and_disconnect_lobby()  # Notify and disconnect all spectators
            lobby_thread.join()  # Wait for the spectator thread to finish
            print("[INFO] Server is shutting down.")


if __name__ == "__main__":
    main()
