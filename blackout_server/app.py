import sys
print("BOOTING_SERVER...", file=sys.stderr)
sys.stderr.flush()

import asyncio
import json
import os
import mimetypes
from pathlib import Path
import websockets
from websockets.asyncio.server import serve as ws_serve
from websockets.http11 import Response

from server.database import init_db, get_leaderboard, get_all_upgrades, save_party
from server.auth import register, login
from server.game_state import create_new_game, GameState
from server.game_engine import process_tick, click_bubble, buy_upgrade

HOST, PORT = "0.0.0.0", 8765
TICK_INTERVAL = 2.0
CLIENT_DIR = Path(__file__).resolve().parent.parent / "client"
active_games, authenticated = {}, {}

async def send_json(ws, data): await ws.send(json.dumps(data))

async def tick_loop():
    while True:
        await asyncio.sleep(TICK_INTERVAL)
        for ws, state in list(active_games.items()):
            if state.result: continue
            process_tick(state)
            await send_json(ws, {"type": "game_update", "state": state.to_dict()})
            if state.result: await send_json(ws, {"type": "game_over", "result": state.result, "score": state.score})

async def handler(ws):
    async for message in ws:
        msg = json.loads(message); action = msg.get("action")
        if action == "register": await send_json(ws, {"type": "auth_result", **register(msg.get("username"), msg.get("password"))})
        elif action == "login":
            res = login(msg.get("username"), msg.get("password"))
            if res["ok"]: authenticated[ws] = res
            await send_json(ws, {"type": "auth_result", **res})
        elif action == "new_game":
            user = authenticated.get(ws)
            if not user: continue
            state = create_new_game(user["user_id"], msg.get("malware_class", "worm"))
            state.difficulty = msg.get("difficulty", "normal")
            active_games[ws] = state
            await send_json(ws, {"type": "game_started", "state": state.to_dict()})
        elif action == "click_bubble":
            state = active_games.get(ws)
            if state: await send_json(ws, {"type": "bubble_feedback", **click_bubble(state, msg.get("bubble_id"))})
        elif action == "buy_upgrade":
            state = active_games.get(ws)
            if state: await send_json(ws, {"type": "upgrade_result", **buy_upgrade(state, msg.get("upgrade_id"))})

async def process_request(path, request):
    p = (CLIENT_DIR / (path.strip("/") or "index.html")).resolve()
    if not p.is_file(): return None
    mt, _ = mimetypes.guess_type(str(p))
    return Response(200, "OK", websockets.datastructures.Headers({"Content-Type": mt or "application/octet-stream"}), p.read_bytes())

async def main():
    init_db()
    async with ws_serve(handler, HOST, PORT, process_request=process_request) as s:
        await asyncio.gather(s.serve_forever(), tick_loop())

if __name__ == "__main__": asyncio.run(main())
