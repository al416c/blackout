
import asyncio
import websockets
import json

async def trigger_bubbles():
    uri = "ws://localhost:8765"
    try:
        async with websockets.connect(uri) as websocket:
            # S'identifier (si nécessaire, ici on assume que le serveur accepte les connexions)
            print("Connecté au serveur pour forcer les bulles...")
            
            # Note: Ce script est purement illustratif car il faudrait être authentifié
            # Je vais plutôt modifier temporairement le server/game_engine.py pour 100% de spawn
            pass
    except Exception as e:
        print(f"Erreur: {e}")

if __name__ == "__main__":
    print("Utilisation du mode manuel: Modification de game_engine.py pour forcer le spawn.")
