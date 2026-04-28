# BLACKOUT - Project Context & Guidelines

## Project Overview
**BLACKOUT** is a real-time cybersecurity game (Red Team vs. Blue Team) where a player (Red Team) acts as a malware attempting to infect a corporate network before the Blue Team (AI or another player) can eradicate it.

- **Type:** Full-stack Web Application (Game)
- **Architecture:** 
  - **Backend:** Python 3.12+ using `asyncio` and `websockets` for real-time logic.
  - **Frontend:** Vanilla HTML/CSS/JavaScript with 2D Canvas for network visualization.
  - **Communication:** Bi-directional JSON over WebSockets.
  - **Database:** SQLite for user persistence, stats, and game configuration.

## Key Technologies
- **Backend:** `websockets`, `bcrypt`, `sqlite3`
- **Frontend:** HTML5 Canvas, Vanilla JS (Revealing Module Pattern)
- **Styling:** Vanilla CSS (Cyberpunk aesthetic)

## Project Structure
- `server/`: Core backend logic.
  - `main.py`: Entry point, WebSocket server, and static file hosting.
  - `game_engine.py`: Centralized game logic (tick processing, commands, upgrades).
  - `game_state.py`: State definitions (Nodes, Zones, GameState).
  - `blue_team_ai.py`: Decision logic for the automated defender.
- `client/`: Frontend assets.
  - `index.html`: Main game interface.
  - `js/`: Modularized game logic (`game.js`, `terminal.js`, `websocket.js`, etc.).
- `docs/`: Design documents, topology specs, and implementation plans.
- `scripts/`: Utility scripts for maintenance and title fixes.

## Building and Running
1. **Environment Setup:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # venv\Scripts\activate   # Windows
   ```
2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
3. **Run Server:**
   ```bash
   python -m server.main
   ```
4. **Access:** Open `http://localhost:8765` in your browser.

## Development Conventions
- **Surgical Updates:** When modifying game logic, focus on `server/game_engine.py` for backend rules and `client/js/` for UI updates.
- **State Management:** The backend is the source of truth. The frontend renders based on `tick` messages received via WebSocket.
- **Terminal Commands:** Commands are registered in `server/game_engine.py`. New commands should be added to `execute_command` (Red) or `execute_blue_command` (Blue).
- **Styling:** Adhere to the existing "Cyberpunk/High-Tech" visual style. CSS variables are defined in `client/css/style.css`.

## Ongoing Roadmap
As of April 2026, the project is undergoing a **Modern Terminal Revamp**:
- Implementation of rich autocompletion in the terminal.
- Detailed shop view with descriptions and grid formatting.
- Refinement of core commands to reduce spam and improve strategic depth.

## Key Files for Reference
- `server/game_engine.py`: The heart of game mechanics and command handling.
- `client/js/game.js`: Responsible for the visual representation of the network.
- `docs/Cahier_des_Charges_BLACKOUT.pdf`: Original project requirements.
