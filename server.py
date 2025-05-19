"""
server.py

This module implements the server-side functionality for the Battleship game. It handles client connections, 
packet creation and parsing, game state management, and spectator notifications.

Functions:
    create_packet(sequence_number, packet_type, payload): Creates a packet with a custom header, checksum, and encrypted payload.
    parse_packet(packet): Parses a packet, verifies its checksum, and decrypts the payload.
    send_packet(conn, sequence_number, packet_type, payload): Sends a packet to a client.
    receive_packet(conn): Receives a packet from a client and parses it.
    notify_and_disconnect_lobby(): Notifies all clients in the lobby that the server is shutting down and disconnects them.
    ask_spectators_to_play(): Asks spectators if they want to play the next game.
    handle_lobby_connections(server_socket): Handles new client connections in the lobby.
    notify_spectators(message, board1=None, board2=None): Sends a message to all spectators, optionally including game boards.
    resume_game(conn, user_id, server_socket, notify_spectators, send_packet, receive_packet, disconnected_players): Resumes a saved game for a reconnecting player.
    save_game_state(filename, game_state): Saves the current game state to a file.
    load_game_state(filename): Loads the game state from a file.
    simulate_packet_transmission_with_errors(error_rate): Simulates packet transmission with artificial errors.
    caesar_encrypt(text, shift): Encrypts text using the Caesar Cipher.
    caesar_decrypt(text, shift): Decrypts text using the Caesar Cipher.
    main(): Entry point for the server application.

Dependencies:
    socket, threading, pickle, struct, zlib, random, queue, run_multi_player_game_online (from battleship.py)
    
Constants:
    HOST: The IP address of the server.
    PORT: The port number of the server.
    SHARED_KEY: The shared key used for Caesar Cipher encryption.

Author: 23509629 (Enrichson Paris) & 23067779 (Jun Hao Dennis Lou)
Date: 19 MAY 2025
"""

import socket
import threading
import pickle
import struct
import zlib
import random
import secrets
from queue import Queue
from battleship import run_multi_player_game_online

HOST = '127.0.0.1'
PORT = 5005
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

SHARED_KEY = 13 

def create_packet(sequence_number, packet_type, payload):
    """
    Constructs a packet with a custom header, CRC32 checksum, and encrypted payload.

    This function takes a sequence number, packet type, and plaintext payload,
    then performs the following steps:
    - Encrypts the payload using a Caesar cipher with a shared key.
    - Encodes the encrypted payload into bytes.
    - Constructs a header containing sequence number, packet type, and payload length.
    - Computes a CRC32 checksum over the header and encrypted payload.
    - Returns the complete packet as a byte sequence.

    Args:
        sequence_number (int): The sequence number to be included in the packet header.
        packet_type (int): An integer indicating the type of the packet (e.g., game data, chat, system control).
        payload (str): The plaintext message to encrypt and include in the packet.

    Returns:
        bytes: The fully assembled and encrypted packet, ready for transmission.
    """
    encrypted_payload = caesar_encrypt(payload, SHARED_KEY)
    payload_bytes = encrypted_payload.encode('utf-8')
    payload_length = len(payload_bytes)
    header = struct.pack('!H B I', sequence_number, packet_type, payload_length)
    checksum = zlib.crc32(header + payload_bytes)
    packet = header + struct.pack('!I', checksum) + payload_bytes
    return packet


def parse_packet(packet):
    """
    Parses a received packet by verifying its checksum and decrypting its payload.

    This function extracts the header, checksum, and encrypted payload from the given
    byte-formatted packet. It verifies the integrity of the packet using CRC32 checksum,
    and decrypts the payload using a Caesar cipher with a shared key. If the checksum
    fails or any exception occurs during parsing, the function logs an error and returns None.

    Args:
        packet (bytes): The raw received packet in bytes. Expected to contain a 7-byte
                        header, a 4-byte checksum, and an encrypted payload.

    Returns:
        tuple: (sequence_number (int), packet_type (int), payload (str))
               - sequence_number: The sequence number extracted from the packet header.
               - packet_type: The type of the packet (e.g., data or ACK).
               - payload: The decrypted string payload.

        None: If packet parsing fails due to corruption, format error, or checksum mismatch.

    Raises:
        None: All exceptions are caught internally and logged.
    """
    try:
        header = packet[:7] 
        checksum = struct.unpack('!I', packet[7:11])[0]
        encrypted_payload = packet[11:]

        computed_checksum = zlib.crc32(header + encrypted_payload)
        if checksum != computed_checksum:
            raise ValueError("[ERROR]: Checksum mismatch, packet discarded.")

        sequence_number, packet_type, payload_length = struct.unpack('!H B I', header)

        encrypted_payload = encrypted_payload.decode('utf-8')
        payload = caesar_decrypt(encrypted_payload, SHARED_KEY)

        # Debug message to log header details and checksum (Uncomment this to see the Packet Structure Info)
        #print(f"[DEBUG] Header Details - Sequence Number: {struct.unpack('!H', header[:2])[0]}, "
        #      f"Packet Type: {struct.unpack('!B', header[2:3])[0]}, "
        #      f"Payload Length: {struct.unpack('!I', header[3:7])[0]}")
        #print(f"[DEBUG] Checksum - Extracted: {checksum}, Recomputed: {computed_checksum}")

        # Log the encrypted and decrypted text (Uncomment this to see the Caesar Cipher Debugging Info)
        #print("============================================")
        #print(f"[DEBUG] Caesar Cipher:")
        #print(f"       ENCRYPTED TEXT: {encrypted_payload}")
        #print(f"       DECRYPTED TEXT: {payload}")
        #print("============================================")
       
        return sequence_number, packet_type, payload
    except Exception as e:
        print(f"[ERROR] Failed to parse packet: {e}")
        return None


def send_packet(conn, sequence_number, packet_type, payload):
    """
    Sends an encrypted and checksummed packet over a socket connection.

    This function creates a properly formatted packet using the given sequence number,
    packet type, and plaintext payload. It then transmits the packet over the provided
    socket connection using the `sendall()` method to ensure all bytes are sent.

    Args:
        conn (socket.socket): The connected socket object used to send data.
        sequence_number (int): The sequence number assigned to the packet.
        packet_type (int): The type identifier for the packet (e.g., game, chat, control).
        payload (str): The plaintext message to be encrypted and sent.

    Returns:
        None

    Raises:
        socket.error: If there is a failure in sending the data over the socket.
    """
    global packet_count
    packet = create_packet(sequence_number, packet_type, payload)
    conn.sendall(packet)
    packet_count += 1 


def receive_packet(conn):
    """
    Receives and parses a complete packet from a socket connection.

    This function attempts to receive a full packet in two stages:
    1. First, it reads the fixed-length header (7 bytes) and checksum (4 bytes).
    2. Then, it reads the variable-length payload based on the payload size
       extracted from the header.

    If successful, it reconstructs the complete packet and delegates parsing
    to `parse_packet()`. It also handles socket timeouts gracefully and logs
    appropriate messages.

    Args:
        conn (socket.socket): A connected socket object from which to read data.

    Returns:
        tuple: A tuple (sequence_number, packet_type, payload) if the packet is valid.
        None: If the connection closes, times out, or the packet is malformed.

    Raises:
        None: All exceptions and socket timeouts are caught and logged internally.
    """
    try:
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
        
        _, _, payload_length = struct.unpack('!H B I', header_and_checksum[:7])

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
    Notifies all connected clients in the lobby of server shutdown and disconnects them.

    This function iterates through all spectator connections, sends a shutdown message
    using `send_packet()`, and then closes each socket connection. It also handles any
    exceptions that occur during the disconnection process and logs the result.

    After notifying and disconnecting all clients, the global `spectators` list is cleared
    to remove stale connection references.
    """
    for conn, addr in spectators:
        try:
            send_packet(conn, 0, 1, "Server is shutting down. Disconnecting...")
            conn.close()
            print(f"[INFO] Disconnected client {addr} from the lobby.")
        except Exception as e:
            print(f"[ERROR] Error while disconnecting client {addr}: {e}")
    spectators.clear()


def ask_spectators_to_play():
    """
    Prompts all connected spectators to indicate if they want to join the next game.

    This function sends a prompt to each spectator asking if they wish to play in the 
    upcoming game. It waits for a response from each client and records those who reply
    with 'y' (case-insensitive) as willing participants. Any spectators who fail to 
    respond or cause an exception are removed from the global spectators list.

    Access to the `spectators` list is thread-safe and protected with `spectators_lock`.
    """
    willing_spectators = []
    with spectators_lock:
        for conn, addr in spectators:
            try:
                send_packet(conn, 0, 6,"Do you want to play the next game? (y/n):")
                response = receive_packet(conn)
                if response and response[2].strip().lower() == 'y':
                    willing_spectators.append((conn, addr))
            except Exception as e:
                print(f"[ERROR] Failed to communicate with spectator {addr}: {e}")
                spectators.remove((conn, addr)) 
    return willing_spectators


def handle_lobby_connections(server_socket):
    """
    Handles incoming client connections in the lobby and categorizes them as players or spectators.

    This function listens for new socket connections and prompts each client to identify
    themselves as a new player, a reconnecting player (by user ID), or a spectator. Based
    on the response, it performs one of the following:
    
    - Reconnects a previously disconnected player and resumes their game session.
    - Assigns a new player ID and places the client in the player queue.
    - Registers the client as a spectator and sends a welcome message.
    
    Invalid or failed inputs result in connection termination.

    This function runs in a loop and is intended to be launched in a background thread.
    It makes use of shared global state including `unique_id_counter`, `disconnected_players`,
    and `spectators`, and accesses shared resources using thread locks.

    Args:
        server_socket (socket.socket): The listening server socket that accepts new connections.
    """
    global unique_id_counter, disconnected_players, spectators

    while True:
        conn, addr = server_socket.accept()
        print(f"[INFO] New client connected from {addr}.")
        send_packet(conn, 0, 1, "Welcome! Are you a new player, reconnecting, or a spectator? (Type 'new', your user ID, or 'spectator'):");
        
        packet = receive_packet(conn)
        if not packet:
            print("[ERROR] Failed to receive user input.")
            conn.close()
            continue

        _, _, user_input = packet

        if user_input.isdigit() and int(user_input) in disconnected_players:
            user_id = int(user_input)
            print(f"[INFO] Player {user_id} attempting to reconnect...")

            send_packet(conn, 0, 3, "Please enter your session token to reconnect:")
            token_packet = receive_packet(conn)
            if not token_packet:
                print("[ERROR] Failed to receive session token.")
                conn.close()
                continue
            _, _, session_token = token_packet

            expected_token = active_players.get(user_id, {}).get("token")
            if session_token != expected_token:
                send_packet(conn, 0, 3, "Invalid session token. Reconnection denied.")
                conn.close()
                print(f"[WARN] Player {user_id} provided invalid session token.")
                continue

            print(f"[INFO] Player {user_id} provided valid session token and is reconnecting...")
         
            active_players[user_id]["conn"] = conn

            threading.Thread(
                target=resume_game,
                args=(conn, user_id, server_socket, notify_spectators, send_packet, receive_packet, disconnected_players),
                daemon=True
            ).start()
            
        elif user_input.lower() == "new" or user_input.lower() == "n":
            user_id = unique_id_counter
            unique_id_counter += 1
            player_queue.put((conn, addr, user_id))
            send_packet(conn, user_id, 3,f"Welcome, Player {user_id}! You are in the queue. Waiting for another player...")
            print(f"[INFO] New player assigned ID {user_id} and added to the queue.")

        elif user_input.lower() == "spectator" or user_input.lower() == "s":
            with spectators_lock:
                spectators.append((conn, addr))
            send_packet(conn, 0, 3,"You are now spectating. You will receive updates about ongoing games.")
            print(f"[INFO] Client {addr} is now spectating.")
            notify_spectators("A new spectator has joined.")

        else:
            send_packet(conn, 0, 3,"Invalid input. Please type 'new', your user ID, or 'spectator'.")
            conn.close()

def notify_spectators(message, board1=None, board2=None):
    """
    Sends a message to all connected spectators, with optional game board updates.

    This function iterates over the current list of spectators and sends a general
    update message using `send_packet()`. If both `board1` and `board2` are provided,
    it additionally sends the visual representation of each player's board.

    Any spectators who fail to receive the message (e.g., due to disconnection) are 
    removed from the global `spectators` list. Access to this list is synchronized 
    using `spectators_lock`.

    Args:
        message (str): A textual message to broadcast to all spectators.
        board1 (str, optional): String representation of Player 1's board.
        board2 (str, optional): String representation of Player 2's board.
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

    
def resume_game(conn, user_id, server_socket, notify_spectators, send_packet,
                receive_packet, disconnected_players):
    """
    Attempts to resume a previously saved multiplayer game session for a reconnecting user.

    This function loads the saved game state from a file and identifies whether the 
    reconnecting user is Player 1 or Player 2. It attempts to recover both player connections 
    and resumes the game session if both players are available. If the other player is still 
    disconnected or the game state is invalid, the resumption fails gracefully.

    The game resumes using the `run_multi_player_game_online` function with the original 
    game state and player identifiers. Spectators are notified of resumed play if applicable.

    Args:
        conn (socket.socket): The socket connection of the reconnecting player.
        user_id (int): The ID of the reconnecting user.
        server_socket (socket.socket): The main server socket for accepting new connections.
        notify_spectators (function): A callback function to send messages to all spectators.
        send_packet (function): Function used to send a message packet to a player.
        receive_packet (function): Function used to receive a message packet from a player.
        disconnected_players (dict): A mapping of user IDs to (addr, conn) for disconnected players.
    """
    try:
        game_state = load_game_state("game_state.pkl")
        if not game_state:
            raise ValueError("Failed to load game state from file.")

        user_id1 = game_state["user_id1"]
        user_id2 = game_state["user_id2"]

        if user_id == user_id1:
            conn1 = active_players.get(user_id1, {}).get("conn") or disconnected_players.get(user_id1, (None, None))[1]
            conn2 = active_players.get(user_id2, {}).get("conn") or disconnected_players.get(user_id2, (None, None))[1]
        elif user_id == user_id2:
            conn2 = active_players.get(user_id2, {}).get("conn") or disconnected_players.get(user_id2, (None, None))[1]
            conn1 = active_players.get(user_id1, {}).get("conn") or disconnected_players.get(user_id1, (None, None))[1]
        else:
            raise ValueError(f"Invalid user_id: {user_id}.")

        if conn1 is None or conn2 is None:
            send_packet(conn, user_id, 3, "The other player has disconnected. The game cannot be resumed.")
            print(f"[ERROR] Cannot resume game: One of the players is disconnected.")
            return

        run_multi_player_game_online(conn1, conn2, notify_spectators, user_id1, user_id2,
                                     server_socket, handle_lobby_connections, send_packet,
                                     receive_packet, disconnected_players, active_players,
                                     resuming_game=True, saved_game_state=game_state)
    except Exception as e:
        print(f"[ERROR] Failed to resume game for Player {user_id}: {e}")
        send_packet(conn, user_id, 3, "Failed to resume your game. Please try again later.")
        conn.close()


def save_game_state(filename, game_state):
    """
    Saves the current game state to a file using pickle serialization.

    This function serializes the provided `game_state` object and writes it to the
    specified file in binary mode. It is used to persist the game session so it can 
    be resumed later in case of player disconnection or server interruption.

    Any exceptions encountered during the file operation are caught and logged.

    Args:
        filename (str): The name of the file to which the game state will be saved.
        game_state (dict): The current game state, including player IDs, boards, turns, etc.
    """
    try:
        with open(filename, 'wb') as f:
            pickle.dump(game_state, f)
        print(f"[INFO] Game state saved to {filename}")
    except Exception as e:
        print(f"[ERROR] Failed to save game state: {e}")


def load_game_state(filename):
    """
    Loads a previously saved game state from a file using pickle deserialization.

    This function attempts to open the specified file and deserialize the contents
    into a Python object representing the saved game state. It is used to restore
    game sessions that were saved during disconnection or server shutdown.

    If the file cannot be read or deserialization fails, an error is logged and
    None is returned.

    Args:
        filename (str): The path to the file containing the serialized game state.

    Returns:
        dict: The deserialized game state object if successful.
        None: If loading fails due to file or deserialization errors.
    """
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
    Simulates packet transmission with artificial bit errors and detects corrupted packets.

    This function loops over all previously sent packets (`packet_count` assumed to be global),
    generates packets using `create_packet`, and randomly injects bit-level corruption based 
    on the specified `error_rate`. It then attempts to parse each packet using `parse_packet`, 
    counting how many are detected as corrupted (i.e., failed checksum validation).

    A statistical summary is printed at the end of the simulation.

    Args:
        error_rate (float): A probability between 0.0 and 1.0 indicating the likelihood that
                            each packet will be corrupted by a single-byte bit flip.

    Returns:
        int: The number of packets flagged as corrupted during parsing.
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

    print("=======================================================================")
    print(f"\n[INFO] Statistical Summary: Simulated packet transmission completed.")
    print(f"Total Packets Sent During Gameplay: {packet_count}")
    print(f"Corrupted Packets Detected: {corrupted_count}")
    print(f"Error Rate: {error_rate * 100:.2f}%")
    print("=======================================================================")
    if packet_count > 0:
        print(f"Detection Rate: {(corrupted_count / packet_count) * 100:.2f}%")
    return corrupted_count

def caesar_encrypt(text, shift):
    """
    Encrypts a string using the Caesar Cipher algorithm with the specified shift.

    This function iterates over each character in the input text and applies a 
    Caesar shift to alphabetic characters (both uppercase and lowercase). 
    Non-alphabetic characters (e.g., digits, punctuation, spaces) are left unchanged.

    Args:
        text (str): The plaintext string to encrypt.
        shift (int): The number of positions to shift each letter by in the alphabet.

    Returns:
        str: The encrypted text where each alphabetic character is shifted by `shift`
             positions, wrapping around the alphabet if necessary.
    """

    encrypted = []
    for char in text:
        if char.isalpha():
            shift_base = ord('A') if char.isupper() else ord('a')
            encrypted.append(chr((ord(char) - shift_base + shift) % 26 + shift_base))
        else:
            encrypted.append(char)  # Non-alphabetic characters are not encrypted

    encrypted_text = ''.join(encrypted)

    return encrypted_text

def caesar_decrypt(text, shift):
    """
    Decrypts a string that was encrypted using the Caesar Cipher with the given shift.

    This function reverses the Caesar Cipher encryption by applying a negative shift
    to the input text. It uses the `caesar_encrypt` function internally with `-shift`.

    Args:
        text (str): The encrypted string to decrypt.
        shift (int): The number of positions the text was originally shifted during encryption.

    Returns:
        str: The decrypted plaintext string.
    """
    return caesar_encrypt(text, -shift)

def main():
    """
    Entry point for starting the multiplayer game server.

    This function initializes and runs the main server loop for a turn-based multiplayer game
    with spectator support. It accepts incoming player connections, manages a queue for pairing
    players, and supports reconnections and rematches. It also handles a dedicated lobby thread
    for accepting extra clients, such as spectators or reconnecting players.

    Game sessions are initiated once two players are available in the queue. After each game,
    the server prompts both players to continue or disconnects them accordingly. If enough
    spectators express interest in playing, they are promoted to player slots.

    The server handles disconnection events, replay prompts, and gracefully shuts down on
    KeyboardInterrupt.

    Global Variables Used:
        game_running (bool): Indicates whether a game session is active.
        unique_id_counter (int): Tracks unique user IDs assigned to players.
        player_queue (queue.Queue): Stores player connection info waiting to be matched.
        spectators (list): List of (conn, addr) tuples for connected spectators.
    """
    global game_running, unique_id_counter, player_queue, spectators

    print(f"[INFO] Server listening on {HOST}:{PORT}")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, PORT))
        s.listen(5)  
        print("[DEBUG] Waiting for players to connect...")

        lobby_thread = threading.Thread(target=handle_lobby_connections,args=(s, ),daemon=True)
        lobby_thread.start()
        print("[INFO] Lobby thread started to handle extra clients.")

        try:
            while True:
                while player_queue.qsize() < 2:
                    print("[INFO] Waiting for two players to join...")
                    threading.Event().wait(1) 

                conn1, addr1, user_id1 = player_queue.get()
                print(f"[INFO] Player 1 connected from {addr1} with ID {user_id1}")
                conn2, addr2, user_id2 = player_queue.get()
                print(f"[INFO] Player 2 connected from {addr2} with ID {user_id2}")
                
                token1 = secrets.token_hex(8)
                token2 = secrets.token_hex(8)
                active_players[user_id1] = {"conn": conn1, "token": token1}
                active_players[user_id2] = {"conn": conn2, "token": token2}

                notify_spectators(f"Game is starting! Player 1 (ID {user_id1}) and Player 2 (ID {user_id2}) are ready to play.\n")

                game_running = True  

                try:
                    while True:
                        token1 = secrets.token_hex(8)
                        token2 = secrets.token_hex(8)
                        active_players[user_id1] = {"conn": conn1, "token": token1}
                        active_players[user_id2] = {"conn": conn2, "token": token2}
                        
                        run_multi_player_game_online(
                        conn1, conn2, notify_spectators, user_id1, user_id2, s,
                        handle_lobby_connections, send_packet, receive_packet,
                        disconnected_players, active_players, token1=token1, token2=token2)
                        try:
                            send_packet(conn2, user_id2, 6, "Waiting for Player 1 to respond...")
                            def get_valid_response(conn, user_id):
                                valid_yes = ["y", "yes"]
                                valid_no = ["n", "no"]
                                while True:
                                    try:
                                        send_packet(conn, user_id, 6, "Do you want to play again? (y/n):")
                                        conn.settimeout(30)
                                        response = receive_packet(conn)
                                        if response is None:
                                            print(f"[INFO] Player {user_id} did not respond to replay prompt. Closing connection.")
                                            try:
                                                conn.close()
                                            except Exception as e:
                                                print(f"[ERROR] Error while closing Player {user_id} connection: {e}")
                                            return "no"
                                        answer = response[2].strip().lower()
                                        if answer in valid_yes + valid_no:
                                            return answer
                                        else:
                                            send_packet(conn, user_id, 6, "Invalid input. Please enter 'y', 'yes', 'n', or 'no'.")
                                    except socket.timeout:
                                        print(f"[INFO] Player {user_id} did not respond to replay prompt in time.")
                                        try:
                                            conn.close()
                                        except Exception as e:
                                            print(f"[ERROR] Error while closing Player {user_id} connection: {e}")
                                        return "no"
                                    finally:
                                        conn.settimeout(None)

                            resp1 = get_valid_response(conn1, user_id1)
                            resp2 = get_valid_response(conn2, user_id2)

                            if resp1 not in ["y", "yes"] or resp2 not in ["y", "yes"]:
                                send_packet(conn1, user_id1, 3, "Game over. A player has chosen not to play again.")
                                send_packet(conn2, user_id2, 3, "Game over. A player has chosen not to play again.")
                                break 

                        except (BrokenPipeError, ConnectionResetError):
                            print("[ERROR] One of the players disconnected during the rematch prompt.")
                            notify_spectators("The game has ended due to a player disconnecting.\n")
                            break

                except Exception as e:
                    print(f"[ERROR] An error occurred during the game: {e}")
                    notify_spectators("The game has ended due to an error.\n")

                finally:
                    game_running = False
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

                    # Simulate packet transmission with errors (Uncomment this for testing)
                    #error_rate = 0.5
                    #simulate_packet_transmission_with_errors(error_rate)
                    
                    willing_spectators = ask_spectators_to_play()
                    if len(willing_spectators) >= 2:
                        print("[INFO] Promoting willing spectators to players for the next game.")
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

            
                    notify_spectators("The game has ended. Thank you for watching!")

        except KeyboardInterrupt:
            print("[INFO] Server shutting down due to KeyboardInterrupt.")
        finally:
            notify_and_disconnect_lobby() 
            lobby_thread.join() 
            print("[INFO] Server is shutting down.")


if __name__ == "__main__":
    main()
