import asyncio
import json
import websockets
import random
import string

async def test_game_flow():
    uri = "ws://localhost:8765/ws"
    # Générer un utilisateur unique pour éviter les conflits
    rand_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    username = f"test_{rand_suffix}"
    
    async with websockets.connect(uri) as websocket:
        print(f"[TEST] Connecté. Test avec user: {username}")
        
        # 1. Register
        await websocket.send(json.dumps({
            "action": "register",
            "username": username,
            "password": "password"
        }))
        resp = await websocket.recv()
        data = json.loads(resp)
        print(f"[TEST] Register: {data.get('ok')} {data.get('error', '')}")
        
        # 2. Login
        await websocket.send(json.dumps({
            "action": "login",
            "username": username,
            "password": "password"
        }))
        resp = await websocket.recv()
        data = json.loads(resp)
        print(f"[TEST] Login: {data.get('ok')}")
        
        if data.get('ok'):
            # 3. New Game
            print("[TEST] Envoi new_game...")
            await websocket.send(json.dumps({
                "action": "new_game",
                "malware_class": "worm",
                "difficulty": "normal"
            }))
            
            # Attendre game_started
            resp = await websocket.recv()
            game_data = json.loads(resp)
            print(f"[TEST] Type: {game_data.get('type')}")
            
            if game_data.get('type') == 'game_started':
                nodes = game_data.get('state', {}).get('nodes', [])
                print(f"[TEST] OK: {len(nodes)} nœuds reçus.")
                # Vérifier si les coordonnées sont valides
                if nodes:
                    n = nodes[0]
                    print(f"[TEST] Coords nœud 0: x={n.get('x')}, y={n.get('y')}")
            else:
                print(f"[TEST] ERREUR: Reçu {game_data.get('type')}")

if __name__ == "__main__":
    try:
        asyncio.run(test_game_flow())
    except Exception as e:
        print(f"[TEST] Crash: {e}")
