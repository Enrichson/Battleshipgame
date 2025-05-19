# BEER Game - Multiplayer with Spectator and Reconnection Support

This project implements a networked multiplayer Battleship game with support for spectators and player reconnection. The game consists of a **server** that manages the game logic and client connections, and a **client** that allows players and spectators to interact with the game.

---

## **Features**
- **Multiplayer Gameplay**: Two players can compete in a turn-based Battleship game.
- **Spectator Mode**: Spectators can watch the game in real-time.
- **Reconnection Support**: Players can reconnect to the game if they disconnect.
- **Session Security**: Session tokens are used to prevent session hijacking.
- **Game State Persistence**: The game state is saved and can be resumed after disconnection.

---

## **File Descriptions**

### **1. `server.py`**
The server-side implementation of the Battleship game. It handles:
- Client connections and disconnections.
- Game state management.
- Spectator notifications.
- Reconnection logic for players.

### **2. `client.py`**
The client-side implementation for players and spectators. It allows:
- Players to place ships, take turns, and interact with the game.
- Spectators to watch the game in real-time.

### **3. `battleship.py`**
Contains the core game logic, including:
- Board management (ship placement, firing logic).
- Game state persistence (saving and loading).
- Multiplayer game loop.

### **4. `README.md`**
This file provides instructions on how to set up and interact with the Battleship game.

---

## **How to Use**

### **1. Prerequisites**
- Python 3.8 or higher installed on your system.
- Basic understanding of how to run Python scripts.
- Ensure all files (`server.py`, `client.py`, `battleship.py`) are in the same directory.

---

### **2. Running the Server and clients**

1. Open a terminal and navigate to the directory containing the files.
2. Open up 5 terminals (1 for server, 4 for clients), by hitting CTRL + SHIFT + 5 (This shortcut will open 1 split terminal)
3. Run the server using the following command:
   ```bash
   python server.py
   ```
4. Run the client using the following command:
   ```bash 
   python client.py
   ```

### **3. Error handling/termination of terminal**
- Should you run into any errors, kill the terminal either via the VSCode interface or using CTRL + C to reset and retry again.
- If you are running on MacOS, since the port number 5000 is by default used by another process (Airdrop). You will need to change the port number initialised on **client.py** and **server.py** to a different port value.

---

# How to Play the Battleship Game

This guide explains how to play the Battleship game as a **player** or a **spectator**. Follow the instructions below to get started.

---

## **1. Starting the Game**

### **For Players**
1. **Run the Client**:
   - Open a terminal and navigate to the project directory.
   - Start the client by running:
     ```bash
     python client.py
     ```
2. **Choose Your Role**:
   - When prompted, type `new` to join as a new player.
   - If reconnecting, enter your **user ID** and **session token** when prompted.

3. **Place Your Ships**:
   - You will be prompted to place your ships on the board.
   - Enter the starting coordinate (e.g., `A1`) and orientation (`horizontal` or `vertical`) for each ship.

4. **Take Turns**:
   - Once the game starts, take turns firing at your opponent's board by entering a coordinate (e.g., `B5`).
   - The server will notify you if your shot was a **hit**, **miss**, or if you **sank a ship**.

5. **Winning the Game**:
   - The game ends when all of one player's ships are sunk.
   - The winner will be announced, and you will be prompted to play again or exit.

---

### **For Spectators**
1. **Run the Client**:
   - Open a terminal and navigate to the project directory.
   - Start the client by running:
     ```bash
     python client.py
     ```
2. **Choose Spectator Mode**:
   - When prompted, type `spectator` to join as a spectator.

3. **Watch the Game**:
   - You will receive real-time updates about the game, including:
     - Player actions (e.g., firing at coordinates).
     - Hits, misses, and sunk ships.
     - The current state of each player's board.
4. **Your Turn to Play**
   - When game ends, and existing players decide to not rematch, you will be prompted with "Do you want to play (Y/N)"
   - Type Y/N if you would like to play and wait for another player to join.

---

## **2. Reconnecting to the Game**

If you disconnect during the game, you can reconnect and resume your session:
1. Run the client again using:
   ```bash
   python client.py
   ```
2. Enter your user ID and session token when prompted. (E.g. player 1 - user ID 1, and a unique 8-byte token session is generated after board has been set.)
3. The server will validate your session and allow you to resume the game afterwards.

---

### Authors
- 23509629 (Enrichson Paris)
- 23067779 (Jun Hao Dennis Lou)
