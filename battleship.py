import random
import select
import pickle

BOARD_SIZE = 10
SHIPS = [("Carrier", 5), ("Battleship", 4), ("Cruiser", 3), ("Submarine", 3),
         ("Destroyer", 2)]


class Board:
    """
    Represents a single Battleship board with hidden ships.
    We store:
      - self.hidden_grid: tracks real positions of ships ('S'), hits ('X'), misses ('o')
      - self.display_grid: the version we show to the player ('.' for unknown, 'X' for hits, 'o' for misses)
      - self.placed_ships: a list of dicts, each dict with:
          {
             'name': <ship_name>,
             'positions': set of (r, c),
          }
        used to determine when a specific ship has been fully sunk.

    In a full 2-player networked game:
      - Each player has their own Board instance.
      - When a player fires at their opponent, the server calls
        opponent_board.fire_at(...) and sends back the result.
    """

    def __init__(self, size=BOARD_SIZE):
        self.size = size
        # '.' for empty water
        self.hidden_grid = [['.' for _ in range(size)] for _ in range(size)]
        # display_grid is what the player or an observer sees (no 'S')
        self.display_grid = [['.' for _ in range(size)] for _ in range(size)]
        self.placed_ships = [
        ]  # e.g. [{'name': 'Destroyer', 'positions': {(r, c), ...}}, ...]

    def place_ships_randomly(self, ships=SHIPS):
        """
        Randomly place each ship in 'ships' on the hidden_grid, storing positions for each ship.
        In a networked version, you might parse explicit placements from a player's commands
        (e.g. "PLACE A1 H BATTLESHIP") or prompt the user for board coordinates and placement orientations; 
        the self.place_ships_manually() can be used as a guide.
        """
        for ship_name, ship_size in ships:
            placed = False
            while not placed:
                orientation = random.randint(
                    0, 1)  # 0 => horizontal, 1 => vertical
                row = random.randint(0, self.size - 1)
                col = random.randint(0, self.size - 1)

                if self.can_place_ship(row, col, ship_size, orientation):
                    occupied_positions = self.do_place_ship(
                        row, col, ship_size, orientation)
                    self.placed_ships.append({
                        'name': ship_name,
                        'positions': occupied_positions
                    })
                    placed = True

    def place_ships_manually_with_clientandserver(self, ships=SHIPS, conn=None, sequence_number=0,
                                                  send_packet=None, receive_packet=None):
        """
        Prompt the client for each ship's starting coordinate and orientation (H or V).
        Validates the placement; if invalid, re-prompts.
        """
        if conn is None or send_packet is None or receive_packet is None:
            raise ValueError("Connection and packet functions must be provided for client interaction.")

        # Inform the client that ship placement is starting
        send_packet(conn, sequence_number, 1, "\nPlease place your ships manually on the board.")
        sequence_number += 1
        send_packet(conn, sequence_number, 1, "YOUR BOARD:\n" + self.get_display_grid())
        sequence_number += 1

        for ship_name, ship_size in ships:
            while True:
                send_packet(conn, sequence_number, 1, f"\nPlacing your {ship_name} (size {ship_size}).")
                sequence_number += 1
                send_packet(conn, sequence_number, 1, "Enter starting coordinate (e.g. A1):")
                sequence_number += 1

                packet = receive_packet(conn)
                if not packet:
                    return False  # Client disconnected or error occurred
                _, _, coord_str = packet

                if coord_str.lower() == 'quit':
                    send_packet(conn, sequence_number, 1, "Game Over: You have quit the game.")
                    return False
                
                if not coord_str or not coord_str.strip():
                    send_packet(conn, sequence_number, 1, "[1] Invalid input. Please enter a coordinate.")
                    sequence_number += 1
                    continue

                try:
                    row, col = parse_coordinate(coord_str)
                    # Validate orientation
                    send_packet(conn, sequence_number, 1, "Enter orientation ('H' for horizontal, 'V' for vertical):")
                    sequence_number += 1

                    packet = receive_packet(conn)
                    if not packet:
                        return False  # Client disconnected or error occurred
                    _, _, orientation_str = packet

                    orientation_str = orientation_str.strip().upper()
                    if orientation_str not in ('H', 'V'):
                        send_packet(conn, sequence_number, 1, "[!] Invalid orientation. Please enter 'H' for horizontal or 'V' for vertical.")
                        sequence_number += 1
                        continue 
                    
                    if not orientation_str or not orientation_str.strip():
                        send_packet(conn, sequence_number, 1, "[!] Invalid input. Please enter 'H' or 'V'.")
                        sequence_number += 1
                        continue

                    orientation = 0 if orientation_str == 'H' else 1
                    if self.can_place_ship(row, col, ship_size, orientation):
                        occupied_positions = self.do_place_ship(row, col, ship_size, orientation)
                        self.placed_ships.append({'name': ship_name, 'positions': occupied_positions})
                        send_packet(conn, sequence_number, 1, f"{ship_name} placed successfully!")
                        sequence_number += 1
                        send_packet(conn, sequence_number, 1, "UPDATED BOARD:\n" + self.get_display_grid())
                        sequence_number += 1
                        break
                    else:
                        send_packet(conn, sequence_number, 1, f"[!] Cannot place {ship_name} at {coord_str}. Try again.")
                        sequence_number += 1
                except ValueError as e:
                    send_packet(conn, sequence_number, 1, f"[!] Invalid input: {e}")
                    sequence_number += 1

        # Send the final board to the client
        send_packet(conn, sequence_number, 1, "YOUR FINAL BOARD:\n" + self.get_display_grid())
        sequence_number += 1
        return True

    def can_place_ship(self, row, col, ship_size, orientation):
        """
        Check if we can place a ship of length 'ship_size' at (row, col)
        with the given orientation (0 => horizontal, 1 => vertical).
        Returns True if the space is free, False otherwise.
        """
        if orientation == 0:  # Horizontal
            if col + ship_size > self.size:
                return False
            for c in range(col, col + ship_size):
                if self.hidden_grid[row][c] != '.':
                    return False
        else:  # Vertical
            if row + ship_size > self.size:
                return False
            for r in range(row, row + ship_size):
                if self.hidden_grid[r][col] != '.':
                    return False
        return True

    def do_place_ship(self, row, col, ship_size, orientation):
        """
        Place the ship on hidden_grid and display_grid by marking 'S', and return the set of occupied positions.
        """
        occupied = set()
        if orientation == 0:  # Horizontal
            for c in range(col, col + ship_size):
                self.hidden_grid[row][c] = 'S'
                self.display_grid[row][c] = 'S'  # Update display grid
                occupied.add((row, c))
        else:  # Vertical
            for r in range(row, row + ship_size):
                self.hidden_grid[r][col] = 'S'
                self.display_grid[r][col] = 'S'  # Update display grid
                occupied.add((r, col))
        return occupied

    def fire_at(self, row, col):
        """
        Fire at (row, col). Return a tuple (result, sunk_ship_name).
        Possible outcomes:
          - ('hit', None)          if it's a hit but not sunk
          - ('hit', <ship_name>)   if that shot causes the entire ship to sink
          - ('miss', None)         if no ship was there
          - ('already_shot', None) if that cell was already revealed as 'X' or 'o'

        The server can use this result to inform the firing player.
        """
        try:
            cell = self.hidden_grid[row][col]
            if cell == 'S':
                # Mark a hit
                self.hidden_grid[row][col] = 'X'
                self.display_grid[row][col] = 'X'
                # Check if that hit sank a ship
                sunk_ship_name = self._mark_hit_and_check_sunk(row, col)
                if sunk_ship_name:
                    return ('hit', sunk_ship_name)  # A ship has just been sunk
                else:
                    return ('hit', None)
            elif cell == '.':
                # Mark a miss
                self.hidden_grid[row][col] = 'o'
                self.display_grid[row][col] = 'o'
                return ('miss', None)
            elif cell == 'X' or cell == 'o':
                return ('already_shot', None)
            else:
                raise ValueError("Unexpected cell value.")
        except IndexError:
            raise ValueError("Firing coordinate out of bounds.")

    def _mark_hit_and_check_sunk(self, row, col):
        """
        Remove (row, col) from the relevant ship's positions.
        If that ship's positions become empty, return the ship name (it's sunk).
        Otherwise return None.
        """
        for ship in self.placed_ships:
            if (row, col) in ship['positions']:
                ship['positions'].remove((row, col))
                if len(ship['positions']) == 0:
                    return ship['name']
                break
        return None

    def all_ships_sunk(self):
        """
        Check if all ships are sunk (i.e. every ship's positions are empty).
        """
        for ship in self.placed_ships:
            if len(ship['positions']) > 0:
                return False
        return True

    def print_display_grid(self, show_hidden_board=False):
        """
        Print the board as a 2D grid.

        If show_hidden_board is False (default), it prints the 'attacker' or 'observer' view:
        - '.' for unknown cells,
        - 'X' for known hits,
        - 'o' for known misses.

        If show_hidden_board is True, it prints the entire hidden grid:
        - 'S' for ships,
        - 'X' for hits,
        - 'o' for misses,
        - '.' for empty water.
        """
        # Decide which grid to print
        grid_to_print = self.hidden_grid if show_hidden_board else self.display_grid

        # Column headers (1 .. N)
        print("  " + "".join(str(i + 1).rjust(2) for i in range(self.size)))
        # Each row labeled with A, B, C, ...
        for r in range(self.size):
            row_label = chr(ord('A') + r)
            row_str = " ".join(grid_to_print[r][c] for c in range(self.size))
            print(f"{row_label:2} {row_str}")

    def get_display_grid(self):
        """
        Return the display grid as a string for sending to players.
        """
        grid_str = "  " + "".join(
            str(i + 1).rjust(2) for i in range(self.size)) + '\n'
        for r in range(self.size):
            row_label = chr(ord('A') + r)
            row_str = " ".join(self.display_grid[r][c]
                               for c in range(self.size))
            grid_str += f"{row_label:2} {row_str}\n"
        return grid_str


def parse_coordinate(coord_str):
    """
    Convert something like 'B5' into zero-based (row, col).
    Example: 'A1' => (0, 0), 'C10' => (2, 9)
    """
    try:
        coord_str = coord_str.strip().upper()
        row_letter = coord_str[0]
        col_digits = coord_str[1:]

        # Validate row letter
        if row_letter < 'A' or row_letter > chr(ord('A') + BOARD_SIZE - 1):
            raise ValueError(
                f"Invalid row letter '{row_letter}'. Must be between A and {chr(ord('A') + BOARD_SIZE - 1)}."
            )

        # Validate column digits
        if not int(col_digits.isdigit()) or len(col_digits) < 1 or len(col_digits) > 2:
            raise ValueError("Invalid format. Must be a letter followed by a number (e.g., A1).")
        

        row = ord(row_letter) - ord('A')
        col = int(col_digits) - 1  # zero-based

        if row < 0 or row >= BOARD_SIZE or col < 0 or col >= BOARD_SIZE:
            raise ValueError("Coordinate out of bounds.")

        return (row, col)
    except Exception as e:
        raise ValueError(f"Failed to parse coordinate '{coord_str}': {e}")


def readline_timeout(conn, timeout):
    """
    Read a line from a socket connection `conn` within `timeout` seconds using select.
    Returns the line (including newline) as bytes, or None if timed out.
    """
    try:
        fd = conn.fileno()
    except Exception:
        return None
    ready, _, _ = select.select([fd], [], [], timeout)
    if not ready:
        return None
    # Read until newline or EOF
    line = b""
    while True:
        chunk = conn.recv(1)
        if not chunk:
            break
        line += chunk
        if chunk == b'\n':
            break
    return line if line else None


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


def run_multi_player_game_online(conn1, conn2, notify_spectators, user_id1, user_id2, server_socket, wait_for_reconnection, send_packet, receive_packet, disconnected_players, active_players, resuming_game=False, saved_game_state=None):
    sequence_number1 = 0
    sequence_number2 = 0
    waiting_for_reconnection = {1: False, 2: False}

    def send_to_player(conn, sequence_number, msg):
        if conn is not None:
            try:
                send_packet(conn, sequence_number, 1, msg)
            except Exception as e:
                print(f"[ERROR] Failed to send to player: {e}")

    def send_to_both(msg):
        send_to_player(conn1, sequence_number1, msg)
        send_to_player(conn2, sequence_number2, msg)

    if resuming_game and saved_game_state:
        # Load the saved game state
        board1 = saved_game_state["board1"]
        board2 = saved_game_state["board2"]
        freshBoard1 = saved_game_state["freshBoard1"]
        freshBoard2 = saved_game_state["freshBoard2"]
        current_turn = saved_game_state["current_turn"]
        timeout_counts = saved_game_state["timeout_counts"]
        print("[INFO] Resuming game from saved state...")
    else:
        # Initialize a new game
        board1 = Board(BOARD_SIZE)
        board2 = Board(BOARD_SIZE)

        if not board1.place_ships_manually_with_clientandserver(SHIPS, conn1, sequence_number1, send_packet, receive_packet):
            send_to_both("Game Over: Player 1 has quit the game.")
            notify_spectators("Player 1 has quit the game.")
            return

        send_to_player(conn1, sequence_number1, "All ships placed! Waiting for Player 2 to place their ships.")
        notify_spectators("Player 1 has placed their ships.")

        if not board2.place_ships_manually_with_clientandserver(SHIPS, conn2, sequence_number2, send_packet, receive_packet):
            send_to_both("Game Over: Player 2 has quit the game.")
            notify_spectators("Game Over: Player 2 has quit the game.")
            return

        freshBoard1 = Board(BOARD_SIZE)
        freshBoard2 = Board(BOARD_SIZE)

        current_turn = 1  # Player 1 starts
        timeout_counts = {1: 0, 2: 0}  # Timeout counts for both players

        # Save the initial game state
        game_state = {
            "board1": board1,
            "board2": board2,
            "freshBoard1": freshBoard1,
            "freshBoard2": freshBoard2,
            "current_turn": 1,  # Player 1 starts
            "timeout_counts": {1: 0, 2: 0},
            "user_id1": user_id1,
            "user_id2": user_id2,
        }
        save_game_state("game_state.pkl", game_state)

        send_to_player(conn1, sequence_number1, "All ships placed! The game is starting.")
        send_to_player(conn2, sequence_number2, "All ships placed! The game is starting.")
        notify_spectators("Game is starting! Player 1 and Player 2 are ready to play.\n")

    active_players[user_id1] = conn1
    active_players[user_id2] = conn2

    game_running = True
    TIMEOUT_DURATION = 10  # Timeout duration in seconds

    try:
        while game_running:
            if current_turn == 1:
                send_to_player(conn1, sequence_number1, "YOUR FIRING BOARD:\n" + freshBoard2.get_display_grid())
                send_to_player(conn1, sequence_number1,"Enter coordinate to fire at (e.g. B5 or 'quit' to exit):")
                send_to_player(conn2, sequence_number2, "Waiting for Player 1...")
                notify_spectators("Player 1 is taking their turn.")

                try:
                    conn1.settimeout(TIMEOUT_DURATION)
                    packet = receive_packet(conn1)

                    if not packet:
                        timeout_counts[1] += 1
                        if timeout_counts[1] == 1:
                            send_to_both("Player 1 took too long. Turn skipped.")
                            notify_spectators("Player 1 took too long. Turn skipped.")
                            current_turn = 2  # Switch to Player 2
                            continue  # Skip Player 1's turn
                        elif timeout_counts[1] == 2:
                            send_to_both("Game Over: Player 1 forfeited the game due to inactivity.")
                            notify_spectators("Game Over: Player 1 forfeited the game due to inactivity.")
                            game_running = False
                            break
                        continue  # If not game over, skip rest of this turn

                    _, _, guess = packet

                    if guess is None:  # Timeout occurred (if your receive_packet returns None on timeout)
                        timeout_counts[1] += 1
                        if timeout_counts[1] == 1:
                            send_to_both("Player 1 took too long. Turn skipped.")
                            notify_spectators("Player 1 took too long. Turn skipped.")
                            current_turn = 2  # Switch to Player 2
                            continue  # Skip Player 1's turn
                        elif timeout_counts[1] == 2:
                            send_to_both("Game Over: Player 1 forfeited the game due to inactivity.")
                            notify_spectators("Game Over: Player 1 forfeited the game due to inactivity.")
                            game_running = False
                            break
                        continue  # If not game over, skip rest of this turn

                    if not guess or not guess.strip():
                        send_to_player(conn1, sequence_number1, "Invalid input. Please enter a coordinate.")
                        continue
                    elif guess.lower() == 'quit':
                        raise ConnectionResetError("Player 1 has quit the game.")

                    timeout_counts[1] = 0  # Reset timeout flag for Player 1

                    try:
                        row, col = parse_coordinate(guess)
                        result, sunk_name = board2.fire_at(row, col)
                        if result == 'hit':
                            freshBoard2.display_grid[row][col] = 'X'
                            if sunk_name:
                                send_to_both(f"Player 1 HIT! Sunk {sunk_name}!")
                                notify_spectators(f"Player 1 HIT! Sunk {sunk_name}!")
                            else:
                                send_to_both("Player 1 HIT!")
                                notify_spectators("Player 1 HIT!")
                        elif result == 'miss':
                            freshBoard2.display_grid[row][col] = 'o'
                            send_to_both("Player 1 MISS!")
                            notify_spectators("Player 1 MISS!")
                        elif result == 'already_shot':
                            send_to_player(conn1, sequence_number1, "You've already fired at that location.")
                            continue

                        # Send Player 1 their own firing board after each move
                        send_to_player(conn1, sequence_number1, "YOUR FIRING BOARD:\n" + freshBoard2.get_display_grid())
                        # Send spectators a copy of the board
                        notify_spectators("PLAYER 1 FIRING BOARD:\n" + board2.get_display_grid())

                        # Check if Player 2's ships are all sunk
                        if board2.all_ships_sunk():
                            send_to_both("Player 1 wins! All Player 2's ships are sunk.")
                            notify_spectators("Player 1 wins! All Player 2's ships are sunk.")
                            game_running = False
                            break
                    except ValueError as e:
                        # handle Invalid coordinate parsing
                        send_to_player(conn1, sequence_number1, f"Invalid coordinate: {e}")
                        sequence_number1 += 1
                        continue

                except (BrokenPipeError, ConnectionResetError):
                    print(f"[INFO] Player {user_id1} disconnected. Saving game state...")
                    send_to_player(conn2, sequence_number2, f"Player 1 disconnected, waiting for reconnection...")
                    game_state = {
                        "board1": board1,
                        "board2": board2,
                        "freshBoard1": freshBoard1,
                        "freshBoard2": freshBoard2,
                        "current_turn": current_turn,
                        "timeout_counts": timeout_counts,
                        "user_id1": user_id1,
                        "user_id2": user_id2,
                    }
                    disconnected_players[user_id1] = (game_state, conn1)
                    conn1.close()
                    save_game_state("game_state.pkl", game_state)

                    try:
                        conn1 = wait_for_reconnection(server_socket, user_id1)
                        if conn1:
                            # Update the active players dictionary and reset timeout
                            active_players[user_id1] = conn1
                            timeout_counts[1] = 0  # Reset timeout counter for Player 1
                            send_packet(conn1, sequence_number1, 1, "You have reconnected. Continuing the game...")
                            send_to_both(f"Player 1 ({user_id1}) has reconnected. Continuing the game...")
                            notify_spectators(f"Player 1 ({user_id1}) has reconnected. Continuing the game...")
                        else:
                            # Handle reconnection failure
                            send_to_both(f"Game over, Player 1 ({user_id1}) did not reconnect.")
                            notify_spectators(f"Game over, Player 1 ({user_id1}) did not reconnect.")
                            active_players.pop(user_id1, None)
                            game_running = False
                            break
                    except Exception as e:
                        print(f"[ERROR] An error occurred during Player 1's reconnection: {e}")
                        send_to_both(f"Game over, Player 1 ({user_id1}) did not reconnect.")
                        notify_spectators(f"Game over, Player 1 ({user_id1}) did not reconnect.")
                        active_players.pop(user_id1, None)
                        game_running = False
                        break
                    continue

            else:
                send_to_player(conn2, sequence_number2, "YOUR FIRING BOARD:\n" + freshBoard1.get_display_grid())
                send_to_player(conn2, sequence_number2,"Enter coordinate to fire at (e.g. B5 or 'quit' to exit):")
                send_to_player(conn1, sequence_number1, "Waiting for Player 2...")
                notify_spectators("Player 2 is taking their turn.")

                try:
                    conn2.settimeout(TIMEOUT_DURATION)
                    packet = receive_packet(conn2)

                    if not packet:
                        timeout_counts[2] += 1
                        if timeout_counts[2] == 1:
                            send_to_both("Player 2 took too long. Turn skipped.")
                            notify_spectators("Player 2 took too long. Turn skipped.")
                            current_turn = 1  # Switch to Player 1
                            continue  # Skip Player 1's turn
                        elif timeout_counts[2] == 2:
                            send_to_both("Game Over: Player 2 forfeited the game due to inactivity.")
                            notify_spectators("Game Over: Player 2 forfeited the game due to inactivity.")
                            game_running = False
                            break
                        continue  # If not game over, skip rest of this turn

                    _, _, guess = packet

                    if guess is None:  # Timeout occurred (if your receive_packet returns None on timeout)
                        timeout_counts[1] += 1
                        if timeout_counts[1] == 1:
                            send_to_both("Player 1 took too long. Turn skipped.")
                            notify_spectators("Player 1 took too long. Turn skipped.")
                            current_turn = 2  # Switch to Player 2
                            continue  # Skip Player 1's turn
                        elif timeout_counts[1] == 2:
                            send_to_both("Game Over: Player 1 forfeited the game due to inactivity.")
                            notify_spectators("Game Over: Player 1 forfeited the game due to inactivity.")
                            game_running = False
                            break
                        continue  # If not game over, skip rest of this turn

                    if not guess or not guess.strip():
                        send_to_player(conn2, sequence_number2, "Invalid input. Please enter a coordinate.")
                        continue
                    elif guess.lower() == 'quit':
                        raise ConnectionResetError("Player 2 has quit the game.")

                    timeout_counts[2] = 0  # Reset timeout flag for Player 2
                    
                    try:
                        row, col = parse_coordinate(guess)
                        result, sunk_name = board1.fire_at(row, col)
                        if result == 'hit':
                            freshBoard1.display_grid[row][col] = 'X'
                            if sunk_name:
                                send_to_both(f"Player 2 HIT! Sunk {sunk_name}!")
                                notify_spectators(f"Player 2 HIT! Sunk {sunk_name}!")
                            else:
                                send_to_both("Player 2 HIT!")
                                notify_spectators("Player 2 HIT!")
                        elif result == 'miss':
                            freshBoard1.display_grid[row][col] = 'o'
                            send_to_both("Player 2 MISS!")
                            notify_spectators("Player 2 MISS!")
                        elif result == 'already_shot':
                            send_to_player(conn2, sequence_number2, "You've already fired at that location.")
                            continue

                        # Send Player 2 their own firing board after each move
                        send_to_player(conn2, sequence_number2, "YOUR FIRING BOARD:\n" + freshBoard1.get_display_grid())
                        # Send spectators a copy of the board
                        notify_spectators("PLAYER 2 FIRING BOARD:\n" + board1.get_display_grid())

                        # Check if Player 1's ships are all sunk
                        if board1.all_ships_sunk():
                            send_to_both("Player 2 wins! All Player 1's ships are sunk.")
                            notify_spectators("Player 2 wins! All Player 1's ships are sunk.")
                            game_running = False
                            break
                        
                    except ValueError as e:
                        # handle Invalid coordinate parsing
                        send_to_player(conn1, sequence_number1, f"Invalid coordinate: {e}")
                        sequence_number1 += 1
                        continue

                except (BrokenPipeError, ConnectionResetError):
                    print(f"[INFO] Player {user_id2} disconnected. Saving game state...")
                    send_to_player(conn1, sequence_number1, f"Player 2 disconnected, waiting for reconnection...")
                    game_state = {
                        "board1": board1,
                        "board2": board2,
                        "freshBoard1": freshBoard1,
                        "freshBoard2": freshBoard2,
                        "current_turn": current_turn,
                        "timeout_counts": timeout_counts,
                        "user_id1": user_id1,
                        "user_id2": user_id2,
                    }
                    disconnected_players[user_id2] = (game_state, conn2)
                    conn2.close()
                    save_game_state("game_state.pkl", game_state)

                    try:
                        conn2 = wait_for_reconnection(server_socket, user_id2)
                        if conn2:
                            # Update the active players dictionary and reset timeout
                            active_players[user_id2] = conn2
                            timeout_counts[2] = 0  # Reset timeout counter for Player 1
                            send_packet(conn2, sequence_number2, 1, "You have reconnected. Continuing the game...")
                            send_to_both(f"Player 2 ({user_id2}) has reconnected. Continuing the game...")
                            notify_spectators(f"Player 2 ({user_id2}) has reconnected. Continuing the game...")
                        else:
                            # Handle reconnection failure
                            send_to_both(f"Game over, Player 2 ({user_id2}) did not reconnect.")
                            notify_spectators(f"Game over, Player 2 ({user_id2}) did not reconnect.")
                            active_players.pop(user_id2, None)
                            game_running = False
                            break
                    except Exception as e:
                        print(f"[ERROR] An error occurred during Player 2's reconnection: {e}")
                        send_to_both(f"Game over, Player 2 ({user_id2}) did not reconnect.")
                        notify_spectators(f"Game over, Player 2 ({user_id2}) did not reconnect.")
                        active_players.pop(user_id2, None)
                        game_running = False
                        break
                    continue

            current_turn = 3 - current_turn  # Switch turns
    finally:
        send_to_both("The game has ended. Thank you for playing!")
        #notify_spectators("The game has ended. Thank you for watching!")
        active_players.pop(user_id1, None)
        active_players.pop(user_id2, None)
