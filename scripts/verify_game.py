import asyncio
import json
import websockets

async def test_game_flow():
    uri = "ws://localhost:8765/ws"
    async with websockets.connect(uri) as websocket:
        print("[TEST] Connecté au serveur.")
        
        # 1. Login (simulé)
        await websocket.send(json.dumps({
            "action": "login",
            "username": "testuser",
            "password": "password"
        }))
        
        resp = await websocket.recv()
        data = json.loads(resp)
        print(f"[TEST] Réponse login: {data.get('type')}")
        
        if data.get('type') == 'auth_result' and data.get('ok'):
            # 2. Nouvelle partie
            print("[TEST] Lancement nouvelle partie...")
            await websocket.send(json.dumps({
                "action": "new_game",
                "malware_class": "worm",
                "difficulty": "normal"
            }))
            
            # Attendre game_started
            resp = await websocket.recv()
            game_data = json.loads(resp)
            print(f"[TEST] Type reçu: {game_data.get('type')}")
            
            if game_data.get('type') == 'game_started':
                state = game_data.get('state', {})
                nodes = state.get('nodes', [])
                print(f"[TEST] Succès ! {len(nodes)} nœuds reçus.")
                if len(nodes) > 0:
                    print(f"[TEST] Premier nœud: {nodes[0]}")
                else:
                    print("[TEST] ERREUR: Aucun nœud dans l'état initial.")
            else:
                print(f"[TEST] ERREUR: Reçu {game_data.get('type')} au lieu de game_started.")
        else:
            print(f"[TEST] Échec auth: {data.get('error')}")

if __name__ == "__main__":
    try:
        asyncio.run(test_game_flow())
    except Exception as e:
        print(f"[TEST] Erreur critique: {e}")
