"""
Moteur de jeu BLACKOUT — Logique de tick et commandes.
"""
import random
import json
from server.game_state import GameState, Bubble, MALWARE_PROFILES
from server.database import get_all_upgrades, get_blueteam_events

def process_tick(state: GameState):
    if state.result: return state
    state.tick += 1
    if state.special_cooldown > 0: state.special_cooldown -= 1
    for k in list(state.command_cooldowns.keys()):
        if state.command_cooldowns[k] > 0: state.command_cooldowns[k] -= 1

    profile = MALWARE_PROFILES[state.malware_class]
    m_tot = state.total_nodes
    if m_tot == 0: return state

    # Difficulté
    d = (state.difficulty or "normal").lower()
    s_m, i_m, p_m, c_r = (0.5, 1.4, 1.15, 0.1) if d=="facile" else (1.55, 0.8, 0.85, 0.28) if d=="difficile" else (1, 1, 1, 0.18)

    # Propagation
    n_inf_val = state.infected_count * (profile["propagation"] + state.propagation_mod) * (state.healthy_count/m_tot) * p_m * 0.25
    new_inf = int(n_inf_val) + (1 if random.random() < (n_inf_val - int(n_inf_val)) else 0)

    cand = []
    for node in state.nodes:
        if node.infected and not node.quarantined:
            for nid in node.connections:
                nb = state.nodes[nid]
                if not nb.infected and not nb.quarantined and not nb.honeypot:
                    if node.sector_id == nb.sector_id: cand.append(nid)
                    elif node.is_gateway or random.random() < (0.01 + state.porosity_mod): cand.append(nid)

    if cand and new_inf > 0:
        for nid in random.sample(cand, min(new_inf, len(set(cand)))): state.nodes[nid].infected = True

    # Ressources
    state.cpu_cycles += state.infected_count * (profile["income_per_node"] + state.income_mod) * 0.025 * i_m + state.passive_income_bonus
    state.it_budget += state.healthy_count * 0.3

    # Méfiance
    stealth = max(0.05, 1.0 - state.stealth_mod)
    state.suspicion = min(100.0, state.suspicion + (state.infected_count * profile["noise_per_machine"] * stealth * 0.12 * s_m) / 3.0)

    # Patch
    if state.suspicion >= 100.0 and not state.patch_deployed:
        state.patch_deployed = True; state.clean_rate = c_r
    if state.patch_deployed:
        to_cl = [n for n in state.nodes if n.infected and not n.quarantined]
        if to_cl:
            for n in random.sample(to_cl, min(max(1, round(len(to_cl)*state.clean_rate)), len(to_cl))): n.infected = False

    _spawn_bubbles(state)
    state.bubbles = [b for b in state.bubbles if b.ttl > 0]
    for b in state.bubbles: b.ttl -= 1
    state.score = state.tick * 10 + state.infected_count * 5
    if state.healthy_count == 0: state.result = "victory"
    elif state.infected_count == 0: state.result = "defeat"
    return state

def _spawn_bubbles(state):
    inf = [n for n in state.nodes if n.infected and not n.quarantined]
    if random.random() < 0.35:
        anc = random.choice(inf) if inf else type('N',(),{'x':450,'y':350})()
        state.bubbles.append(Bubble(id=state.next_bubble_id, x=round(anc.x+random.uniform(-40,40),1), y=round(anc.y+random.uniform(-40,40),1), kind=random.choice(["breach","exfiltration"]), value=random.randint(6,18), ttl=10))
        state.next_bubble_id += 1

def click_bubble(state, bid):
    for i, b in enumerate(state.bubbles):
        if b.id == bid:
            if b.kind in ("breach","exfiltration"): state.cpu_cycles += b.value; res = {"type":"attacker","gained":b.value}
            else: state.suspicion = min(100.0, state.suspicion + b.value*0.35); res = {"type":"defender"}
            state.bubbles.pop(i); return res
    return {"error":"Bulle introuvable."}

def buy_upgrade(state, uid):
    up = next((u for u in get_all_upgrades() if u["id"] == uid), None)
    if not up or state.cpu_cycles < up["cost"] or uid in state.purchased_upgrades: return {"ok":False}
    state.cpu_cycles -= up["cost"]; state.purchased_upgrades.append(uid)
    eff = up["effect_json"]
    if "propagation_bonus" in eff: state.propagation_mod += eff["propagation_bonus"]
    if "stealth" in eff: state.stealth_mod += eff["stealth"]
    if "passive_income" in eff: state.passive_income_bonus += eff["passive_income"]
    if "reveal_sectors" in eff: state.reveal_sectors = True
    if "porosity_bonus" in eff: state.porosity_mod += eff["porosity_bonus"]
    state.stealth_mod += up.get("stealth_mod", 0)
    return {"ok":True, "remaining_cycles":round(state.cpu_cycles,1)}
