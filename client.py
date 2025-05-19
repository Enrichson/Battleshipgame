import socket
import threading
from server import send_packet, receive_packet

HOST = '127.0.0.1'
PORT = 5003
Running = True
Waiting_for_input = False


def receive_messages(sock):
    """
    Continuously receive messages from the server and print them.
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

            # If the server prompts for input, set the flag
            if any(prompt in message for prompt in [
                    "Enter starting coordinate", "Enter orientation",
                    "Enter coordinate to fire at",
                    "Do you want to play again?",
                    "Welcome! Are you a new player, reconnecting, or a spectator? (Type 'new', your user ID, or 'spectator'):",
                    "Do you want to play the next game? (y/n):",
                    "Please enter your user ID to reconnect:"
            ]):
                Waiting_for_input = True

        except Exception as e:
            print(f"[ERROR] Error receiving message: {e}")
            Running = False
            break


def main():
    global Running, Waiting_for_input

    # Connect to the server
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((HOST, PORT))
        print("[INFO] Connected to the server.")

        # Start a thread to receive messages from the server
        threading.Thread(target=receive_messages, args=(sock, ),
                         daemon=True).start()

        try:
            sequence_number = 0
            while Running:
                if Waiting_for_input:
                    # Get user input and send it to the server
                    user_input = input(">> ").strip()
                    send_packet(sock, sequence_number, 6, user_input)
                    sequence_number += 1
                    Waiting_for_input = False

                    # If the user enters "quit", stop the client
                    if user_input.lower() == "quit":
                        print("[INFO] Quitting the game...")
                        Running = False
                        Waiting_for_input = False
                        break

        except KeyboardInterrupt:
            # Handle Ctrl+C gracefully
            print("\n[INFO] KeyboardInterrupt detected. Exiting...")
            Running = False
            Waiting_for_input = False
        finally:
            print("[INFO] Cleaning up resources...")
            sock.close()
            print("[INFO] Resources cleaned up. Goodbye!")


if __name__ == "__main__":
    main()
