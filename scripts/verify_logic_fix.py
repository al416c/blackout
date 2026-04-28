
import sys
import os

# Add the project root to sys.path
sys.path.append(os.getcwd())

from server.game_state import create_new_game
from server.game_engine import execute_command, execute_blue_command
from server.database import init_db

def test_help_formatting():
    init_db()
    state = create_new_game(1, "worm", mode="solo")
    
    # Test Red Help
    res = execute_command(state, "help")
    output = res.get("output", "")
    print("--- RED HELP ---")
    print(output)
    assert "+" + "-" * 10 in output
    assert "| BLACKOUT TERMINAL" in output
    assert "install <id>" in output
    
    # Test Blue Help
    res = execute_blue_command(state, "help")
    output = res.get("output", "")
    print("\n--- BLUE HELP ---")
    print(output)
    assert "+" + "-" * 10 in output
    assert "| BLUE TEAM DEFENSIVE PROTOCOLS" in output

def test_install_by_id():
    init_db()
    state = create_new_game(1, "worm", mode="solo")
    state.cpu_cycles = 1000  # Give enough cycles
    
    # We need to know a valid upgrade ID from the DB. 
    # Usually ID 1 exists.
    res = execute_command(state, "install 1")
    output = res.get("output", "")
    print("\n--- INSTALL 1 ---")
    print(output)
    # If it fails with "already bought" it's also fine for the ID parsing test
    assert "Module" in output or "Amelioration deja achetee" in output or "injecté avec succès" in output

if __name__ == "__main__":
    try:
        test_help_formatting()
        test_install_by_id()
        print("\n[VERIFICATION] All tests passed!")
    except Exception as e:
        print(f"\n[VERIFICATION] Failed: {e}")
        sys.exit(1)
