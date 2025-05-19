"""
client.py - Command-line client for multiplayer game with spectator and reconnection support.

This script connects to a game server via TCP, listens for messages, and interacts with the user
based on prompts received from the server. It handles both player and spectator modes, and allows
reconnection by entering a user ID.

Core Features:
- Connects to the server using a socket on HOST:PORT.
- Starts a background thread to continuously receive and process packets from the server.
- Detects prompts for input and enables user interaction in real time.
- Sends user responses back to the server using a Caesar-encrypted custom packet format.
- Handles graceful shutdown via KeyboardInterrupt or quit command.

Global Flags:
- `Running` (bool): Controls the main loop of the client.
- `Waiting_for_input` (bool): Indicates when the server is expecting user input.

Modules Required:
- socket
- threading
- server (must define send_packet and receive_packet functions)

Author: 23509629 (Enrichson Paris) & 23067779 (Jun Hao Dennis Lou)
Date: 19 MAY 2025
"""

import socket
import threading
from server import send_packet, receive_packet

HOST = '127.0.0.1'
PORT = 5000
Running = True
Waiting_for_input = False


def receive_messages(sock):
    """
    Continuously receive messages from the server and print them.

    This function runs in a separate thread and listens for incoming packets from the server. It processes
    the packets and prints the server's messages to the console. If the server prompts for user input, 
    the `Waiting_for_input` flag is set to True.

    Args:
        sock (socket.socket): The socket object used to communicate with the server.

    Raises:
        Exception: If an error occurs while receiving messages from the server.

    Side Effects:
        - Prints server messages to the console.
        - Updates the `Waiting_for_input` and `Running` global variables.
    """
    global Waiting_for_input, Running
    while Running:
        try:
            packet = receive_packet(sock)
            if not packet:
                print("[INFO] Server disconnected.")
                Running = False
                break

            sequence_number, packet_type, message = packet
            print(message.strip())

            if any(prompt in message for prompt in [
                    "Enter starting coordinate", "Enter orientation",
                    "Enter coordinate to fire at",
                    "Do you want to play again?",
                    "Welcome! Are you a new player, reconnecting, or a spectator? (Type 'new', your user ID, or 'spectator'):",
                    "Do you want to play the next game? (y/n):",
                    "Please enter your user ID to reconnect:",
                    "Please enter your session token to reconnect:"
            ]):
                Waiting_for_input = True

        except Exception as e:
            print(f"[ERROR] Error receiving message: {e}")
            Running = False
            break


def main():
    """
    Entry point for the client application.

    This function establishes a connection to the server, starts a thread to receive messages, and handles
    user input during gameplay. The client communicates with the server using the `send_packet` and 
    `receive_packet` functions.

    Raises:
        KeyboardInterrupt: If the user presses Ctrl+C to exit the application.

    Side Effects:
        - Connects to the server.
        - Starts a thread to receive messages from the server.
        - Processes user input and sends it to the server.
        - Cleans up resources upon exit.
    """
    global Running, Waiting_for_input

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((HOST, PORT))
        print("[INFO] Connected to the server.")

        threading.Thread(target=receive_messages, args=(sock, ),
                         daemon=True).start()

        try:
            sequence_number = 0
            while Running:
                if Waiting_for_input:
                    user_input = input(">> ").strip()
                    send_packet(sock, sequence_number, 6, user_input)
                    sequence_number += 1
                    Waiting_for_input = False

                    if user_input.lower() == "quit":
                        print("[INFO] Quitting the game...")
                        Running = False
                        Waiting_for_input = False
                        break

        except KeyboardInterrupt:
            print("\n[INFO] KeyboardInterrupt detected. Exiting...")
            Running = False
            Waiting_for_input = False
        finally:
            print("[INFO] Cleaning up resources...")
            sock.close()
            print("[INFO] Resources cleaned up. Goodbye!")


if __name__ == "__main__":
    main()
