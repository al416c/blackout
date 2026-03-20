"""
Serveur WebSocket principal de BLACKOUT.

Sert aussi les fichiers statiques du client via HTTP.
Gère l'authentification, les sessions de jeu et le tick loop.
"""

import asyncio
import json
import os
import mimetypes
from pathlib import Path

import websockets
from websockets.asyncio.server import serve as ws_serve
from websockets.http11 import Response
from websockets.datastructures import Headers

from server.database import (
    init_db, get_leaderboard, get_all_upgrades, get_blueteam_events,
    save_party, update_party, end_party, update_user_stats,
)
from server.auth import register, login
from server.game_state import create_new_game, GameState
from server.game_engine import process_tick, click_bubble, buy_upgrade


# ── Configuration ────────────────────────────────────────────────────
HOST = "0.0.0.0"
PORT = 8765
# Tick un peu plus rapide pour donner une sensation de jeu plus vivant.
TICK_INTERVAL = 1.5  # secondes entre chaque tick
CLIENT_DIR = Path(__file__).resolve().parent.parent / "client"

# Sessions actives : websocket → GameState
active_games: dict = {}
# Sessions authentifiées : websocket → user info
authenticated: dict = {}


# ── Serveur de fichiers statiques (HTTP) ─────────────────────────────

async def process_request(connection, request):
    """Sert les fichiers statiques du dossier client/ via HTTP.
    Retourne None pour laisser passer au WebSocket, ou un Response pour HTTP."""
    path = request.path

    if path == "/ws":
        return None  # laisser passer au WebSocket

    # Rediriger / vers /index.html
    if path == "/" or path == "":
        path = "/index.html"

    file_path = CLIENT_DIR / path.lstrip("/")

    if file_path.is_file():
        content_type, _ = mimetypes.guess_type(str(file_path))
        if content_type is None:
            content_type = "application/octet-stream"

        body = file_path.read_bytes()
        headers = Headers({
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
            "Cache-Control": "no-cache",
        })
        return Response(200, "OK", headers, body)

    return Response(404, "Not Found", Headers(), b"404 Not Found")


# ── Gestion des messages WebSocket ───────────────────────────────────

async def send_json(ws, data: dict):
    await ws.send(json.dumps(data))


async def handler(ws):
    """Gestionnaire principal de connexion WebSocket."""
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await send_json(ws, {"type": "error", "message": "JSON invalide."})
                continue

            action = msg.get("action")

            if action == "register":
                result = register(msg.get("username", ""), msg.get("password", ""))
                if result["ok"]:
                    authenticated[ws] = {"user_id": result["user_id"], "username": result["username"]}
                await send_json(ws, {"type": "auth_result", **result})

            elif action == "login":
                result = login(msg.get("username", ""), msg.get("password", ""))
                if result["ok"]:
                    authenticated[ws] = {"user_id": result["user_id"], "username": result["username"]}
                await send_json(ws, {"type": "auth_result", **result})

            elif action == "leaderboard":
                lb = get_leaderboard()
                await send_json(ws, {"type": "leaderboard", "data": lb})

            elif action == "get_upgrades":
                upgrades = get_all_upgrades()
                # Filtrer les upgrades par classe de malware de la partie en cours
                state = active_games.get(ws)
                if state:
                    malware = state.malware_class
                    upgrades = [u for u in upgrades
                                if not u["effect_json"].get("allowed_malware")
                                or malware in u["effect_json"]["allowed_malware"]]
                await send_json(ws, {"type": "upgrades_list", "data": upgrades})

            elif action == "new_game":
                user = authenticated.get(ws)
                if not user:
                    await send_json(ws, {"type": "error", "message": "Non authentifié."})
                    continue

                malware_class = msg.get("malware_class", "worm")
                if malware_class not in ("worm", "trojan", "ransomware", "rootkit"):
                    malware_class = "worm"

                state = create_new_game(user["user_id"], malware_class)
                # Appliquer la difficulté envoyée par le client
                difficulty = msg.get("difficulty", "normal")
                if difficulty not in ("facile", "normal", "difficile"):
                    difficulty = "normal"
                state.difficulty = difficulty
                party_id = save_party(user["user_id"], malware_class, state.to_json())
                state.party_id = party_id
                active_games[ws] = state

                await send_json(ws, {"type": "game_started", "state": state.to_dict()})

            elif action == "command":
                # Commandes texte depuis le terminal
                user = authenticated.get(ws)
                state = active_games.get(ws)
                if not user or not state:
                    await send_json(ws, {"type": "command_result", "error": "Aucune partie active."})
                    continue
                from server.game_engine import execute_command
                result = execute_command(state, msg.get("line", ""))
                await send_json(ws, {"type": "command_result", **result})

            elif action == "click_bubble":
                state = active_games.get(ws)
                if not state:
                    await send_json(ws, {"type": "error", "message": "Pas de partie en cours."})
                    continue
                feedback = click_bubble(state, msg.get("bubble_id", -1))
                await send_json(ws, {"type": "bubble_feedback", **feedback})

            elif action == "buy_upgrade":
                state = active_games.get(ws)
                if not state:
                    await send_json(ws, {"type": "error", "message": "Pas de partie en cours."})
                    continue
                result = buy_upgrade(state, msg.get("upgrade_id", -1))
                await send_json(ws, {"type": "upgrade_result", **result})

            elif action == "ping":
                await send_json(ws, {"type": "pong"})

            else:
                await send_json(ws, {"type": "error", "message": f"Action inconnue: {action}"})

    except websockets.ConnectionClosed:
        pass
    finally:
        # Nettoyage
        if ws in active_games:
            state = active_games[ws]
            if state.party_id and state.result is None:
                state.result = "defeat"
                end_party(state.party_id, "defeat", state.score)
                user = authenticated.get(ws)
                if user:
                    update_user_stats(user["user_id"], False, state.score, state.infected_count)
            del active_games[ws]
        authenticated.pop(ws, None)


# ── Boucle de tick ───────────────────────────────────────────────────

async def tick_loop():
    """Exécute un tick de jeu pour toutes les parties actives."""
    while True:
        await asyncio.sleep(TICK_INTERVAL)

        disconnected = []
        for ws, state in list(active_games.items()):
            if state.result is not None:
                continue

            try:
                process_tick(state)

                # Sauvegarder en BDD
                if state.party_id:
                    update_party(state.party_id, state.to_json(), state.score)

                # Envoyer l'état au client
                await send_json(ws, {"type": "tick", "state": state.to_dict()})

                # Fin de partie
                if state.result is not None:
                    if state.party_id:
                        end_party(state.party_id, state.result, state.score)
                        user = authenticated.get(ws)
                        if user:
                            update_user_stats(
                                user["user_id"],
                                state.result == "victory",
                                state.score,
                                state.infected_count,
                            )
                    await send_json(ws, {"type": "game_over", "result": state.result, "score": state.score})

            except websockets.ConnectionClosed:
                disconnected.append(ws)

        for ws in disconnected:
            active_games.pop(ws, None)
            authenticated.pop(ws, None)


# ── Point d'entrée ───────────────────────────────────────────────────

async def main():
    init_db()
    print(f"[BLACKOUT] Base de données initialisée.")
    print(f"[BLACKOUT] Serveur démarré sur http://localhost:{PORT}")
    print(f"[BLACKOUT] WebSocket sur ws://localhost:{PORT}/ws")
    print(f"[BLACKOUT] Fichiers statiques depuis {CLIENT_DIR}")

    async with ws_serve(
        handler,
        HOST,
        PORT,
        process_request=process_request,
    ) as server:
        # Lancer la boucle de tick en parallèle
        asyncio.create_task(tick_loop())
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
