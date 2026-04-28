"""
Serveur WebSocket principal de BLACKOUT.

Sert les fichiers statiques via HTTP et gere :
  - Authentification et sessions
  - Parties solo (active_games)
  - Parties duo / solo-vs-IA (active_rooms)
  - Boucle de tick globale
"""

import asyncio
import json
import secrets
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
    get_all_config, get_config, set_config, delete_config,
)
from server.auth import register, login
from server.game_state import create_new_game, GameState, DuoRoom
from server.game_engine import process_tick, click_bubble, buy_upgrade, apply_blue_action
from server.blue_team_ai import BlueTeamAI


HOST          = "0.0.0.0"
PORT          = 8765
TICK_INTERVAL = 2.0
CLIENT_DIR    = Path(__file__).resolve().parent.parent / "client"

# Parties solo : ws -> GameState
active_games: dict = {}

# Parties duo / solo-vs-IA : room_code -> DuoRoom
active_rooms: dict[str, DuoRoom] = {}

# Lookup rapide ws -> room_code (pour les deux roles)
ws_to_room: dict = {}

# Sessions authentifiées : ws -> {user_id, username}
authenticated: dict = {}

_blue_ai = BlueTeamAI()


# ── Helpers ──────────────────────────────────────────────────────────

def _get_state(ws) -> GameState | None:
    """Trouve l'etat de jeu pour un WebSocket (solo ou room)."""
    if ws in active_games:
        return active_games[ws]
    code = ws_to_room.get(ws)
    if code and code in active_rooms:
        return active_rooms[code].state
    return None


def _get_room(ws) -> DuoRoom | None:
    code = ws_to_room.get(ws)
    return active_rooms.get(code) if code else None


def _get_role(ws) -> str:
    """Retourne 'red' ou 'blue' selon la position du ws dans sa room."""
    room = _get_room(ws)
    if room and room.blue_ws == ws:
        return "blue"
    return "red"


# ── Fichiers statiques (HTTP) ─────────────────────────────────────────

async def process_request(connection, request):
    path = request.path
    if path == "/ws":
        return None
    if path in ("/", ""):
        path = "/index.html"

    file_path = CLIENT_DIR / path.lstrip("/")
    if file_path.is_file():
        content_type, _ = mimetypes.guess_type(str(file_path))
        if content_type is None:
            content_type = "application/octet-stream"
        body    = file_path.read_bytes()
        headers = Headers({
            "Content-Type":   content_type,
            "Content-Length": str(len(body)),
            "Cache-Control":  "no-cache",
        })
        return Response(200, "OK", headers, body)
    return Response(404, "Not Found", Headers(), b"404 Not Found")


# ── Helpers WebSocket ─────────────────────────────────────────────────

async def send_json(ws, data: dict):
    await ws.send(json.dumps(data))


# ── Fin de partie pour une room ───────────────────────────────────────

async def _handle_room_over(room: DuoRoom, code: str):
    state = room.state
    if state.party_id:
        end_party(state.party_id, state.result, state.score)
    if room.red_user:
        update_user_stats(room.red_user["user_id"], state.result == "victory", state.score, state.infected_count)

    try:
        await send_json(room.red_ws, {"type": "game_over", "result": state.result, "score": state.score, "role": "red"})
    except Exception:
        pass

    if room.blue_ws and not room.blue_is_ai:
        blue_result = "defeat" if state.result == "victory" else "victory"
        try:
            await send_json(room.blue_ws, {"type": "game_over", "result": blue_result, "score": state.score, "role": "blue"})
        except Exception:
            pass


# ── Gestionnaire WebSocket ────────────────────────────────────────────

async def handler(ws):
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await send_json(ws, {"type": "error", "message": "JSON invalide."})
                continue

            action = msg.get("action")

            # ── Auth ──────────────────────────────────────────────────
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

            # ── Leaderboard / config ──────────────────────────────────
            elif action == "leaderboard":
                await send_json(ws, {"type": "leaderboard", "data": get_leaderboard()})

            elif action == "get_upgrades":
                upgrades = get_all_upgrades()
                state    = _get_state(ws)
                if state:
                    malware  = state.malware_class
                    upgrades = [u for u in upgrades
                                if not u["effect_json"].get("allowed_malware")
                                or malware in u["effect_json"]["allowed_malware"]]
                await send_json(ws, {"type": "upgrades_list", "data": upgrades})

            elif action == "get_config":
                await send_json(ws, {"type": "config_list", "data": get_all_config()})

            elif action == "set_config":
                user = authenticated.get(ws)
                if not user:
                    await send_json(ws, {"type": "error", "message": "Non authentifie."}); continue
                key, value = msg.get("key", "").strip(), str(msg.get("value", "")).strip()
                if not key or not value:
                    await send_json(ws, {"type": "error", "message": "Cle ou valeur manquante."}); continue
                set_config(key, value)
                await send_json(ws, {"type": "config_updated", "key": key, "value": value})

            elif action == "delete_config":
                user = authenticated.get(ws)
                if not user:
                    await send_json(ws, {"type": "error", "message": "Non authentifie."}); continue
                key     = msg.get("key", "").strip()
                deleted = delete_config(key)
                await send_json(ws, {"type": "config_deleted", "key": key, "ok": deleted})

            # ── Partie solo ───────────────────────────────────────────
            elif action == "new_game":
                user = authenticated.get(ws)
                if not user:
                    await send_json(ws, {"type": "error", "message": "Non authentifie."}); continue

                malware_class = msg.get("malware_class", "worm")
                if malware_class not in ("worm", "trojan", "ransomware", "rootkit"):
                    malware_class = "worm"
                difficulty = msg.get("difficulty", "normal")
                if difficulty not in ("facile", "normal", "difficile"):
                    difficulty = "normal"

                state              = create_new_game(user["user_id"], malware_class, mode="solo")
                state.difficulty   = difficulty
                party_id           = save_party(user["user_id"], malware_class, state.to_json())
                state.party_id     = party_id
                active_games[ws]   = state

                await send_json(ws, {"type": "game_started", "state": state.to_dict(), "role": "red"})

            # ── Partie duo / solo-vs-IA (créateur = Red Team) ─────────
            elif action == "create_room":
                user = authenticated.get(ws)
                if not user:
                    await send_json(ws, {"type": "error", "message": "Non authentifie."}); continue

                malware_class = msg.get("malware_class", "worm")
                if malware_class not in ("worm", "trojan", "ransomware", "rootkit"):
                    malware_class = "worm"
                difficulty = msg.get("difficulty", "normal")
                if difficulty not in ("facile", "normal", "difficile"):
                    difficulty = "normal"
                mode = msg.get("mode", "duo")  # "duo" | "solo_ai"

                blue_is_ai = (mode == "solo_ai")
                game_mode  = "duo" if not blue_is_ai else "solo"

                state             = create_new_game(user["user_id"], malware_class, mode=game_mode)
                state.difficulty  = difficulty
                party_id          = save_party(user["user_id"], malware_class, state.to_json())
                state.party_id    = party_id

                code              = secrets.token_hex(3).upper()
                room              = DuoRoom(
                    code=code, state=state,
                    red_ws=ws, blue_is_ai=blue_is_ai,
                    red_user=user,
                )
                active_rooms[code] = room
                ws_to_room[ws]     = code

                if blue_is_ai:
                    # Démarre immédiatement pour solo-vs-IA
                    await send_json(ws, {
                        "type": "game_started", "state": state.to_dict(),
                        "role": "red", "room_code": code, "vs_ai": True,
                    })
                else:
                    await send_json(ws, {"type": "room_created", "room_code": code})

            elif action == "join_room":
                user = authenticated.get(ws)
                if not user:
                    await send_json(ws, {"type": "error", "message": "Non authentifie."}); continue

                code = msg.get("room_code", "").upper().strip()
                room = active_rooms.get(code)

                if not room:
                    await send_json(ws, {"type": "join_result", "ok": False, "error": "Salle introuvable."}); continue
                if room.blue_ws is not None:
                    await send_json(ws, {"type": "join_result", "ok": False, "error": "Salle deja pleine."}); continue
                if room.blue_is_ai:
                    await send_json(ws, {"type": "join_result", "ok": False, "error": "Cette salle est reservee a l'IA."}); continue

                room.blue_ws   = ws
                room.blue_user = user
                ws_to_room[ws] = code

                state_dict = room.state.to_dict()
                await send_json(room.red_ws, {"type": "game_started", "state": state_dict, "role": "red", "room_code": code})
                await send_json(ws,          {"type": "game_started", "state": state_dict, "role": "blue", "room_code": code})

            # ── Actions en jeu (commun solo + duo) ────────────────────
            elif action == "command":
                user  = authenticated.get(ws)
                state = _get_state(ws)
                if not user or not state:
                    await send_json(ws, {"type": "command_result", "error": "Aucune partie active."}); continue
                from server.game_engine import execute_command
                result = execute_command(state, msg.get("line", ""))
                await send_json(ws, {"type": "command_result", **result})

            elif action == "click_bubble":
                state = _get_state(ws)
                if not state:
                    await send_json(ws, {"type": "error", "message": "Pas de partie en cours."}); continue
                role     = _get_role(ws)
                feedback = click_bubble(state, msg.get("bubble_id", -1), role)
                await send_json(ws, {"type": "bubble_feedback", **feedback})

            elif action == "buy_upgrade":
                state = _get_state(ws)
                if not state:
                    await send_json(ws, {"type": "error", "message": "Pas de partie en cours."}); continue
                result = buy_upgrade(state, msg.get("upgrade_id", -1))
                await send_json(ws, {"type": "upgrade_result", **result})

            # ── Actions Blue Team (humain uniquement) ─────────────────
            elif action == "blue_action":
                state = _get_state(ws)
                if not state:
                    await send_json(ws, {"type": "error", "message": "Pas de partie active."}); continue
                result = apply_blue_action(state, msg)
                await send_json(ws, {"type": "blue_action_result", **result})

            elif action == "ping":
                await send_json(ws, {"type": "pong"})

            else:
                await send_json(ws, {"type": "error", "message": f"Action inconnue: {action}"})

    except websockets.ConnectionClosed:
        pass
    finally:
        # Nettoyage partie solo
        if ws in active_games:
            state = active_games[ws]
            if state.result is None:
                state.result = "defeat"
                if state.party_id:
                    end_party(state.party_id, "defeat", state.score)
                user = authenticated.get(ws)
                if user:
                    update_user_stats(user["user_id"], False, state.score, state.infected_count)
            del active_games[ws]

        # Nettoyage room
        code = ws_to_room.pop(ws, None)
        if code and code in active_rooms:
            room = active_rooms[code]
            if room.red_ws == ws:
                # Red Team déconnectée : notifier Blue et fermer la room
                if room.blue_ws and not room.blue_is_ai:
                    try:
                        await send_json(room.blue_ws, {"type": "error", "message": "L'adversaire s'est deconnecte."})
                    except Exception:
                        pass
                    ws_to_room.pop(room.blue_ws, None)
                del active_rooms[code]
            elif room.blue_ws == ws:
                room.blue_ws = None
                try:
                    await send_json(room.red_ws, {"type": "error", "message": "L'adversaire s'est deconnecte."})
                except Exception:
                    pass

        authenticated.pop(ws, None)


# ── Boucle de tick ───────────────────────────────────────────────────

async def tick_loop():
    while True:
        await asyncio.sleep(TICK_INTERVAL)

        # Ticks pour les rooms (duo + solo-vs-IA)
        for code, room in list(active_rooms.items()):
            state = room.state
            if state.result is not None:
                continue
            try:
                process_tick(state)

                # IA Blue Team : décision et application des actions
                if room.blue_is_ai:
                    for blue_action in _blue_ai.decide(state):
                        apply_blue_action(state, blue_action)

                if state.party_id:
                    update_party(state.party_id, state.to_json(), state.score)

                state_dict = state.to_dict()

                try:
                    await send_json(room.red_ws, {"type": "tick", "state": state_dict, "role": "red"})
                except Exception:
                    pass

                if room.blue_ws and not room.blue_is_ai:
                    try:
                        await send_json(room.blue_ws, {"type": "tick", "state": state_dict, "role": "blue"})
                    except Exception:
                        pass

                if state.result is not None:
                    await _handle_room_over(room, code)

            except Exception as e:
                print(f"[tick] Erreur room {code}: {e}")

        # Ticks pour les parties solo
        disconnected = []
        for ws, state in list(active_games.items()):
            if state.result is not None:
                continue
            try:
                process_tick(state)

                if state.party_id:
                    update_party(state.party_id, state.to_json(), state.score)

                await send_json(ws, {"type": "tick", "state": state.to_dict(), "role": "red"})

                if state.result is not None:
                    if state.party_id:
                        end_party(state.party_id, state.result, state.score)
                    user = authenticated.get(ws)
                    if user:
                        update_user_stats(user["user_id"], state.result == "victory", state.score, state.infected_count)
                    await send_json(ws, {"type": "game_over", "result": state.result, "score": state.score, "role": "red"})

            except websockets.ConnectionClosed:
                disconnected.append(ws)

        for ws in disconnected:
            active_games.pop(ws, None)
            authenticated.pop(ws, None)


# ── Point d'entrée ───────────────────────────────────────────────────

async def main():
    init_db()
    print(f"[BLACKOUT] Base de donnees initialisee.")
    print(f"[BLACKOUT] Serveur sur http://localhost:{PORT}")
    print(f"[BLACKOUT] WebSocket sur ws://localhost:{PORT}/ws")

    async with ws_serve(handler, HOST, PORT, process_request=process_request) as server:
        asyncio.create_task(tick_loop())
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
