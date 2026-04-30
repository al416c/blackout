"""
Moteur de jeu BLACKOUT — logique de chaque tick.

Propagation : les noeuds d'une zone verrouillée ne peuvent pas être infectés normalement.
              Seul le routeur de la zone peut être cracké (chance indépendante par tick).
              Infecter le routeur déverrouille la zone.
"""
import random
import json
from server.game_state import GameState, Bubble, MALWARE_PROFILES, ROUTER_INFECTION_CHANCE
from server.database import get_all_upgrades, get_blueteam_events

# Formatting constants for terminal output
BOLD = "\x1b[1m"
DIM  = "\x1b[2m"
RESET = "\x1b[0m"
RED = "\x1b[1;31m"
YELLOW = "\x1b[1;33m"
BLUE = "\x1b[1;34m"
GREEN = "\x1b[1;36m"


def _zones_by_id(state: GameState) -> dict:
    return {z.id: z for z in (state.zones or [])}


def _unlocked_candidates(state: GameState) -> list:
    """Noeuds sains dans des zones déverrouillées (pour les capacités spéciales)."""
    zmap = _zones_by_id(state)
    return [
        n for n in state.nodes
        if not n.infected and not n.quarantined and not n.honeypot
        and (not zmap or zmap.get(n.zone_id) is None or zmap[n.zone_id].unlocked)
    ]


def _build_qte_challenge(state: GameState, zone) -> dict:
    mc = state.malware_class
    commands = {
        "worm": {
            "LAN":  {"command": "worm deploy stealth_payload --zone lan", "bonus": {"type": "cpu", "value": 25}, "bonus_text": "+25 CPU Cycles"},
            "SRV":  {"command": "worm seed --target srv",             "bonus": {"type": "propagation", "value": 0.08}, "bonus_text": "+8% propagation"},
            "DB":   {"command": "worm inject --db --force",          "bonus": {"type": "passive_income", "value": 1.8}, "bonus_text": "+1.8 passive income"},
            "SCADA": {"command": "worm swarm --scada --silent",     "bonus": {"type": "cpu", "value": 35}, "bonus_text": "+35 CPU Cycles"},
        },
        "trojan": {
            "LAN":  {"command": "trojan backdoor install --lan",      "bonus": {"type": "cpu", "value": 25}, "bonus_text": "+25 CPU Cycles"},
            "SRV":  {"command": "trojan deploy launcher --srv",       "bonus": {"type": "propagation", "value": 0.08}, "bonus_text": "+8% propagation"},
            "DB":   {"command": "trojan dump-db --target db",        "bonus": {"type": "passive_income", "value": 1.8}, "bonus_text": "+1.8 passive income"},
            "SCADA": {"command": "trojan seed --scada",              "bonus": {"type": "cpu", "value": 35}, "bonus_text": "+35 CPU Cycles"},
        },
        "ransomware": {
            "LAN":  {"command": "ransomware encrypt --lan",          "bonus": {"type": "cpu", "value": 25}, "bonus_text": "+25 CPU Cycles"},
            "SRV":  {"command": "ransomware ransom --srv",           "bonus": {"type": "propagation", "value": 0.08}, "bonus_text": "+8% propagation"},
            "DB":   {"command": "ransomware lock --db",             "bonus": {"type": "passive_income", "value": 1.8}, "bonus_text": "+1.8 passive income"},
            "SCADA": {"command": "ransomware blast --scada",        "bonus": {"type": "cpu", "value": 35}, "bonus_text": "+35 CPU Cycles"},
        },
        "rootkit": {
            "LAN":  {"command": "rootkit stealth --lan",             "bonus": {"type": "cpu", "value": 25}, "bonus_text": "+25 CPU Cycles"},
            "SRV":  {"command": "rootkit patch --srv",               "bonus": {"type": "propagation", "value": 0.08}, "bonus_text": "+8% propagation"},
            "DB":   {"command": "rootkit hide --db",                "bonus": {"type": "passive_income", "value": 1.8}, "bonus_text": "+1.8 passive income"},
            "SCADA": {"command": "rootkit persist --scada",         "bonus": {"type": "cpu", "value": 35}, "bonus_text": "+35 CPU Cycles"},
        },
    }
    template = commands.get(mc, {}).get(zone.name)
    if not template:
        return None

    return {
        "zone_id": zone.id,
        "zone_name": zone.name,
        "expected_command": template["command"],
        "prompt": (
            f"QTE UNLOCK: Zone {zone.name} débloquée. Tapez exactement: {template['command']}"
        ),
        "bonus_text": template["bonus_text"],
        "bonus_effect": template["bonus"],
        "remaining_ticks": 8,
    }


def _grant_qte_bonus(state: GameState) -> str:
    qte = state.pending_qte
    if not qte:
        return ""
    effect = qte["bonus_effect"]
    if effect["type"] == "cpu":
        state.cpu_cycles += effect["value"]
        return f"QTE réussi — bonus reçu: {qte['bonus_text']}"
    if effect["type"] == "propagation":
        state.propagation_mod += effect["value"]
        return f"QTE réussi — bonus reçu: {qte['bonus_text']}"
    if effect["type"] == "passive_income":
        state.passive_income_bonus += effect["value"]
        return f"QTE réussi — bonus reçu: {qte['bonus_text']}"
    return "QTE réussi. Bonus appliqué."


def process_tick(state: GameState) -> GameState:
    """Avance l'etat de jeu d'un tick."""
    if state.result is not None:
        return state

    state.tick += 1
    if state.special_cooldown > 0:
        state.special_cooldown -= 1

    for key in list(state.command_cooldowns.keys()):
        if state.command_cooldowns[key] > 0:
            state.command_cooldowns[key] -= 1

    # Décrémenter les pare-feux actifs
    for key in list(state.firewalled_nodes.keys()):
        state.firewalled_nodes[key] -= 1
        if state.firewalled_nodes[key] <= 0:
            del state.firewalled_nodes[key]

    profile = MALWARE_PROFILES[state.malware_class]
    m_tot = state.total_nodes
    if m_tot == 0:
        return state

    m_inf    = state.infected_count
    m_saines = state.healthy_count

    diff = (state.difficulty or "normal").lower()
    if diff == "facile":
        suspicion_mult        = 0.50
        income_mult           = 1.40
        propagation_mult      = 1.15
        difficulty_clean_rate = 0.10
    elif diff == "difficile":
        suspicion_mult        = 1.55
        income_mult           = 0.80
        propagation_mult      = 0.85
        difficulty_clean_rate = 0.28
    else:
        suspicion_mult        = 1.00
        income_mult           = 1.00
        propagation_mult      = 1.00
        difficulty_clean_rate = 0.18

    # Nombre de nouvelles infections ce tick
    t_inf = profile["propagation"]
    m_mod = state.propagation_mod
    ratio = m_saines / m_tot if m_tot > 0 else 0

    # Propagation ralentie (multiplicateur global 0.7)
    n_inf = m_inf * (t_inf + m_mod) * ratio * propagation_mult * 0.7
    whole = int(n_inf)
    frac  = n_inf - whole
    new_infections = whole + (1 if random.random() < frac else 0)

    # Propagation avec gestion des zones
    zmap = _zones_by_id(state)

    normal_candidates: set = set()   # noeuds dans zones déverrouillées
    router_candidates: set = set()   # routeurs de zones verrouillées

    for node in state.nodes:
        if node.infected and not node.quarantined:
            for neighbor_id in node.connections:
                neighbor = state.nodes[neighbor_id]
                if neighbor.infected or neighbor.quarantined or neighbor.honeypot:
                    continue

                if zmap:
                    zone = zmap.get(neighbor.zone_id)
                    if zone and not zone.unlocked:
                        if neighbor.is_router:
                            router_candidates.add(neighbor_id)
                        continue

                normal_candidates.add(neighbor_id)

    # Propagation normale (zones déverrouillées)
    if normal_candidates and new_infections > 0:
        to_infect = random.sample(list(normal_candidates), min(new_infections, len(normal_candidates)))
        for nid in to_infect:
            state.nodes[nid].infected = True

    # Tentatives indépendantes de craquage des routeurs verrouillés
    for nid in router_candidates:
        router = state.nodes[nid]
        zone = zmap.get(router.zone_id)
        if not zone:
            continue
        base_chance = ROUTER_INFECTION_CHANCE.get(zone.security_level, 0.05)
        
        # Le bonus de craquage de routeur (issu des upgrades de transmission)
        # est crucial pour passer les zones de haut niveau.
        crack_bonus = getattr(state, 'router_crack_bonus', 0.0)
        
        # Chance ajustée : prend en compte le modificateur global + le bonus spécifique aux routeurs
        adjusted = (base_chance + crack_bonus) * (1.0 + state.propagation_mod * 0.5) * propagation_mult
        
        if random.random() < adjusted:
            router.infected = True

    # Déverrouillage des zones dont le routeur vient d'être infecté
    for zone in (state.zones or []):
        if not zone.unlocked and zone.router_id is not None:
            if state.nodes[zone.router_id].infected:
                zone.unlocked = True
                if not zone.qte_triggered:
                    zone.qte_triggered = True
                    if state.pending_qte is None:
                        qte = _build_qte_challenge(state, zone)
                        if qte:
                            state.pending_qte = qte
                            state.pending_terminal_events.append({
                                "type": "qte_event",
                                "event": "prompt",
                                "message": qte["prompt"],
                                "zone": qte["zone_name"],
                                "remaining_ticks": qte["remaining_ticks"],
                            })

    # Gérer le compte à rebours de la QTE
    if state.pending_qte:
        state.pending_qte["remaining_ticks"] -= 1
        if state.pending_qte["remaining_ticks"] <= 0:
            state.pending_terminal_events.append({
                "type": "qte_event",
                "event": "failed",
                "message": (
                    f"QTE expirée pour la zone {state.pending_qte['zone_name']}. "
                    "Le bonus est perdu, mais la zone reste déverrouillée."
                ),
                "zone": state.pending_qte["zone_name"],
            })
            state.pending_qte = None

    # Revenus Red Team
    income = profile["income_per_node"]
    state.cpu_cycles += state.infected_count * (income + state.income_mod) * 0.05 * income_mult
    state.cpu_cycles += state.passive_income_bonus

    # Budget Blue Team (régénération passive)
    # Moins agressive si la suspicion est basse (< 20%)
    ai_reactivity = 0.2 if state.suspicion < 20 else 0.5
    state.it_budget += state.healthy_count * ai_reactivity

    # Bruit et méfiance : Croissance exponentielle douce
    # Faible au début, augmente plus vite avec la taille du botnet
    b_machine          = profile["noise_per_machine"]
    stealth_factor     = max(0.05, 1.0 - state.stealth_mod)
    
    # Formule exponentielle : (nbe_noeuds ^ 1.3) pour un effet courbe
    effective_noise    = (state.infected_count ** 1.3) * b_machine * 0.4
    suspicion_increase = effective_noise * 0.15 * suspicion_mult
    
    # Réduction passive de suspicion (certaines upgrades pourraient booster ça)
    passive_reduction  = getattr(state, 'passive_stealth_reduction', 0.05)
    
    state.suspicion    = max(0.0, min(100.0, state.suspicion + suspicion_increase - passive_reduction))

    # Événements Blue Team automatiques : Seuils respectés
    blue_events = get_blueteam_events()
    for event in blue_events:
        # L'IA ne déclenche rien si suspicion trop basse (< 25%) sauf si déjà en cours
        if state.suspicion >= event["trigger_threshold"] and state.suspicion > 25:
            effect = event["effect_json"]
            eid    = event["id"]
            already_triggered = eid in state.triggered_events

            if effect.get("trap_node") and not any(n.honeypot for n in state.nodes):
                healthy_nodes = [
                    n for n in state.nodes
                    if not n.infected and not n.quarantined
                    and (not zmap or zmap.get(n.zone_id) is None or zmap[n.zone_id].unlocked)
                ]
                if healthy_nodes:
                    random.choice(healthy_nodes).honeypot = True

            if effect.get("quarantine") and (state.tick - state.quarantine_last_tick) >= 10:
                infected_nodes = [n for n in state.nodes if n.infected and not n.quarantined]
                if infected_nodes:
                    iso_count     = max(1, int(len(infected_nodes) * effect.get("isolation_rate", 0.1)))
                    to_quarantine = random.sample(infected_nodes, min(iso_count, len(infected_nodes)))
                    for node in to_quarantine:
                        node.quarantined = True
                    state.quarantine_last_tick = state.tick

            if "propagation_penalty" in effect and not already_triggered:
                state.propagation_mod += effect["propagation_penalty"]
                state.triggered_events.append(eid)

            if "detection_rate" in effect and not already_triggered:
                state.suspicion = min(100.0, state.suspicion + effect["detection_rate"] * 7)
                if eid not in state.triggered_events:
                    state.triggered_events.append(eid)

    # Patch de sécurité automatique (méfiance = 100%)
    if state.suspicion >= 100.0 and not state.patch_deployed:
        state.patch_deployed = True
        state.clean_rate     = difficulty_clean_rate

    if state.patch_deployed:
        m_nettoyees   = max(1, round(state.infected_count * state.clean_rate))
        infected_list = [n for n in state.nodes if n.infected and not n.quarantined]
        if infected_list:
            to_clean = random.sample(infected_list, min(m_nettoyees, len(infected_list)))
            for node in to_clean:
                node.infected = False

    _spawn_bubbles(state)
    state.bubbles = [b for b in state.bubbles if b.ttl > 0]
    for b in state.bubbles:
        b.ttl -= 1

    state.score = state.tick * 10 + state.infected_count * 5

    if state.healthy_count == 0 and state.quarantined_count == 0:
        state.result  = "victory"
        state.score  += 1000
    elif state.infected_count == 0:
        state.result = "defeat"

    return state


def _spawn_bubbles(state: GameState):
    """Fait apparaître des bulles cliquables près des noeuds infectés."""
    if random.random() < 0.25:
        infected = [n for n in state.nodes if n.infected and not n.quarantined]
        if infected:
            anc = random.choice(infected)
            x = round(anc.x + random.uniform(-60, 60), 1)
            y = round(anc.y + random.uniform(-60, 60), 1)
        else:
            x = round(random.uniform(80, 800), 1)
            y = round(random.uniform(80, 600), 1)
        kind  = random.choice(["breach", "exfiltration"])
        value = random.randint(6, 18)
        state.bubbles.append(Bubble(
            id=state.next_bubble_id, x=x, y=y,
            kind=kind, value=value, ttl=5,
        ))
        state.next_bubble_id += 1

    if random.random() < 0.12:
        kind  = random.choice(["log_analysis", "patch_deploy"])
        value = random.randint(3, 12)
        state.bubbles.append(Bubble(
            id=state.next_bubble_id,
            x=round(random.uniform(80, 800), 1),
            y=round(random.uniform(80, 600), 1),
            kind=kind, value=value, ttl=5,
        ))
        state.next_bubble_id += 1


def click_bubble(state: GameState, bubble_id: int, role: str = "red") -> dict:
    for i, b in enumerate(state.bubbles):
        if b.id == bubble_id:
            state.bubbles.pop(i)
            if role == "blue":
                if b.kind in ("log_analysis", "patch_deploy"):
                    state.it_budget += b.value
                    return {"type": "defender", "kind": b.kind, "gained": b.value}
                return {"type": "ignored", "kind": b.kind}
            else:
                if b.kind in ("breach", "exfiltration"):
                    state.cpu_cycles += b.value
                    return {"type": "attacker", "kind": b.kind, "gained": b.value}
                suspicion_delta = b.value * 0.35
                state.suspicion = min(100.0, state.suspicion + suspicion_delta)
                return {"type": "defender", "kind": b.kind, "suspicion_added": suspicion_delta}
    return {"error": "Bulle introuvable."}


def apply_blue_action(state: GameState, action: dict) -> dict:
    kind  = action.get("action")
    costs = {"scan": 15, "honeypot": 30, "quarantine": 20, "patch": 50}
    cost  = costs.get(kind, 0)

    if cost > 0 and state.it_budget < cost:
        return {"ok": False, "error": f"Budget IT insuffisant ({int(state.it_budget)}/{cost} requis)."}

    if kind == "scan":
        state.it_budget -= cost
        infected_ids = [n.id for n in state.nodes if n.infected and not n.quarantined]
        return {"ok": True, "action": "scan", "infected_ids": infected_ids, "it_budget": round(state.it_budget, 1)}

    if kind == "honeypot":
        node_id = action.get("node_id")
        if node_id is None or not (0 <= node_id < len(state.nodes)):
            return {"ok": False, "error": "Noeud invalide."}
        node = state.nodes[node_id]
        if node.infected or node.quarantined or node.honeypot:
            return {"ok": False, "error": "Ce noeud ne peut pas recevoir de honeypot."}
        node.honeypot = True
        state.it_budget -= cost
        return {"ok": True, "action": "honeypot", "node_id": node_id, "it_budget": round(state.it_budget, 1)}

    if kind == "quarantine":
        node_id = action.get("node_id")
        if node_id is None or not (0 <= node_id < len(state.nodes)):
            return {"ok": False, "error": "Noeud invalide."}
        node = state.nodes[node_id]
        if not node.infected or node.quarantined:
            return {"ok": False, "error": "Ce noeud n'est pas infecte ou est deja en quarantaine."}
        node.quarantined = True
        state.it_budget -= cost
        return {"ok": True, "action": "quarantine", "node_id": node_id, "it_budget": round(state.it_budget, 1)}

    if kind == "patch":
        if state.patch_deployed:
            return {"ok": False, "error": "Patch deja deploye."}
        state.patch_deployed = True
        state.clean_rate     = 0.22
        state.it_budget     -= cost
        return {"ok": True, "action": "patch", "it_budget": round(state.it_budget, 1)}

    return {"ok": False, "error": "Action inconnue."}


# ── Helpers cooldown terminal ─────────────────────────────────────────

def _cd(state: GameState, key: str) -> int:
    return state.command_cooldowns.get(key, 0)


def _setcd(state: GameState, key: str, ticks: int):
    state.command_cooldowns[key] = ticks


# ── Terminal Red Team ─────────────────────────────────────────────────

def execute_command(state: GameState, line: str) -> dict:
    """Interprète une ligne de commande du terminal (Red Team)."""
    raw = (line or "").strip()
    if not raw:
        return {"ok": False, "output": "Aucune commande saisie."}

    # Gestion de la QTE de déverrouillage
    if state.pending_qte and raw.lower() == state.pending_qte["expected_command"].lower():
        message = _grant_qte_bonus(state)
        state.pending_qte = None
        return {"ok": True, "output": message}

    # Cheat code (debug)
    if raw == "-niter cheagger":
        state.cpu_cycles = 99999
        return {"ok": True, "output": "[OVERRIDE] CPU Cycles -> 99 999. Domination totale."}

    tokens = raw.split()
    cmd    = tokens[0].lower()
    args   = tokens[1:]

    # ── Système d'aide ────────────────────────────────────────────────
    if cmd in ("help", "?", "aide"):
        mc = state.malware_class
        rows = [
            ("help",            "Afficher cette aide"),
            ("status",          "État du malware et du réseau"),
            ("shop",            "Afficher la boutique d'évolution"),
            ("install <id>",    "Acheter une amélioration"),
            ("hack",            "Capacité spéciale de classe"),
            ("zones",           "État détaillé des zones réseau"),
            ("clear",           "Effacer l'écran"),
        ]

        title = f"BLACKOUT TERMINAL — {mc.upper()} PROTOCOLS"
        cmd_w = max(len(r[0]) for r in rows)
        lines = [f"{name.ljust(cmd_w)} — {desc}" for name, desc in rows]
        
        # Calculate width based on lines and title
        inner_w = max(len(title), *(len(l) for l in lines))
        
        sep = "+" + "-" * (inner_w + 2) + "+"
        boxed = [sep, f"| {title.ljust(inner_w)} |", sep]
        boxed += [f"| {l.ljust(inner_w)} |" for l in lines]
        boxed.append(sep)
        return {"ok": True, "output": "\n".join(boxed)}

    # ── Commandes de base ─────────────────────────────────────────────

    if cmd in ("status", "statut"):
        hack_str = "PRÊT" if state.special_cooldown <= 0 else f"{state.special_cooldown}t"
        unlocked = sum(1 for z in state.zones if z.unlocked) if state.zones else 0
        total_z  = len(state.zones) if state.zones else 0
        ratio = round(state.infected_count/state.total_nodes*100 if state.total_nodes>0 else 0, 1)
        
        return {"ok": True, "output": (
            f"[STATUS] T:{state.tick} | CPU:{int(state.cpu_cycles)} | SUSP:{round(state.suspicion, 1)}% | "
            f"INF:{state.infected_count}/{state.total_nodes} ({ratio}%) | "
            f"HACK:{hack_str} | ZONES:{unlocked}/{total_z} | PATCH:{'ON' if state.patch_deployed else 'OFF'}"
        )}

    if cmd == "zones":
        if not state.zones: return {"ok": True, "output": "Aucune zone définie."}
        lines = ["ZONES RÉSEAU:"]
        for zone in state.zones:
            zone_nodes = [n for n in state.nodes if n.zone_id == zone.id]
            infected   = sum(1 for n in zone_nodes if n.infected and not n.quarantined)
            total      = len(zone_nodes)
            status = "DÉBLOQUÉ" if zone.unlocked else f"VERROUILLÉ (SEC.LVL {zone.security_level})"
            lines.append(f"  [{zone.name}] {zone.label.ljust(25)} — {status} [{infected}/{total} infectés]")
        return {"ok": True, "output": "\n".join(lines)}

    if cmd == "shop":
        return {"ok": True, "output": "[SYSTEM] Accès à la base de modules. Utilisez 'install <id>'."}

    # ── Actions stratégiques ─────────────────────────────────────────
    if cmd == "nmap":
        flags = " ".join(args)
        if "-sS" in flags and "-Pn" in flags:
            if _cd(state, "nmap_stealth") > 0:
                return {"ok": False, "output": f"[nmap] Recharge — {_cd(state, 'nmap_stealth')}t restants."}
            state.cpu_cycles += 5
            state.suspicion = max(0, state.suspicion - 1.5)
            _setcd(state, "nmap_stealth", 8)
            return {"ok": True, "output": "Scan furtif terminé. (+5 CPU, méfiance -1.5%)"}
        return {"ok": False, "output": "Usage: nmap -sS -Pn"}

    if cmd == "phishing" and args and args[0].lower() == "start":
        if _cd(state, "phishing") > 0:
            return {"ok": False, "output": f"[phishing] Recharge — {_cd(state, 'phishing')}t restants."}
        gain = max(5, int(state.infected_count * 0.8))
        state.cpu_cycles += gain
        _setcd(state, "phishing", 12)
        return {"ok": True, "output": f"Campagne réussie. (+{gain} CPU Cycles)"}

    if raw.lower().startswith("cat /etc/shadow"):
        if _cd(state, "shadow") > 0:
            return {"ok": False, "output": f"[shadow] Recharge — {_cd(state, 'shadow')}t restants."}
        state.cpu_cycles += 12
        state.suspicion = min(100, state.suspicion + 3.0)
        _setcd(state, "shadow", 15)
        return {"ok": True, "output": "Hashes extraits. (+12 CPU, méfiance +3.0%)"}

    if cmd in ("install", "upgrade"):
        if not args: return {"ok": False, "output": f"Usage: {cmd} <nom|id>"}
        target = " ".join(args).lower()
        upgrades = get_all_upgrades()
        
        # Try finding by name or ID (explicit ID check)
        found = None
        for u in upgrades:
            if target in u["name"].lower():
                found = u
                break
            try:
                if int(target) == u["id"]:
                    found = u
                    break
            except ValueError:
                pass

        if not found: return {"ok": False, "output": f"Module '{target}' inconnu."}
        
        res = buy_upgrade(state, found["id"])
        if res.get("ok"):
            return {"ok": True, "output": f"Module '{found['name']}' injecté avec succès. (CPU restant: {int(state.cpu_cycles)})"}
        return {"ok": False, "output": res.get("error", "Échec de l'injection.")}

    # ── Hack Spécial ────────────────────────────────────────────────
    if cmd in ("hack", "special"):
        if state.special_cooldown > 0:
            return {"ok": False, "output": f"Hack en recharge ({state.special_cooldown}t)."}

        mc = state.malware_class
        if mc == "worm":
            candidates = _unlocked_candidates(state)
            targets = random.sample(candidates, min(4, len(candidates)))
            for n in targets: n.infected = True
            state.special_cooldown = 15
            state.suspicion = min(100.0, state.suspicion + 5.0)
            return {"ok": True, "output": f"[WORM] Propagation forcée sur {len(targets)} nœuds. (cd: 15)"}

        if mc == "trojan":
            state.suspicion = max(0.0, state.suspicion - 25.0)
            state.special_cooldown = 20
            return {"ok": True, "output": "[TROJAN] Traces effacées. Méfiance -25%. (cd: 20)"}

        if mc == "ransomware":
            state.cpu_cycles += 200
            state.special_cooldown = 25
            state.suspicion = min(100.0, state.suspicion + 8.0)
            return {"ok": True, "output": "[RANSOMWARE] Paiement forcé. +200 CPU. (cd: 25)"}

        if mc == "rootkit":
            state.suspicion = 0.0
            state.special_cooldown = 30
            return {"ok": True, "output": "[ROOTKIT] Logs système remis à zéro. (cd: 30)"}

    return {"ok": False, "output": f"Commande '{cmd}' inconnue. Tapez 'help'."}


# ── Terminal Blue Team ────────────────────────────────────────────────

def execute_blue_command(state: GameState, line: str) -> dict:
    """Interprete une ligne de commande du terminal (Blue Team uniquement)."""
    raw = (line or "").strip()
    if not raw:
        return {"ok": False, "output": "Aucune commande saisie."}

    if raw == "-niter cheagger":
        state.it_budget = 99999
        return {"ok": True, "output": "[OVERRIDE] IT Budget -> 99 999. Defenses illimitees."}

    tokens = raw.split()
    cmd    = tokens[0].lower()
    args   = tokens[1:]

    if cmd in ("help", "?", "aide"):
        rows = [
            ("help",               "Affiche cette aide."),
            ("status",             "Etat du reseau et budget IT."),
            ("audit",              "Rapport complet de toutes les zones."),
            ("scan",               "Scan reseau — detecte les infectes (15 IT, cd 4t)."),
            ("honeypot <node_id>", "Piege sur un noeud sain (30 IT)."),
            ("quarantine <id>",    "Isole un noeud infecte (20 IT)."),
            ("patch",              "Deploie un patch securite global (50 IT)."),
            ("firewall <node_id>", "Protege un noeud contre l'infection (25 IT, 10t)."),
            ("isolate <zone>",     "Quarantaine de tous les infectes d'une zone (30 IT)."),
            ("analyze <node_id>",  "Analyse les connexions d'un noeud."),
            ("log suspicion",      "Affiche le niveau de suspicion actuel."),
        ]
        title = "BLUE TEAM DEFENSIVE PROTOCOLS"
        cmd_w = max(len(r[0]) for r in rows)
        lines = [f"{BOLD}{name.ljust(cmd_w)}{RESET} — {desc}" for name, desc in rows]
        
        output = f"{BOLD}{title}{RESET}\n" + "\n".join(lines)
        return {"ok": True, "output": output}

    if cmd in ("status", "statut"):
        unlocked = sum(1 for z in state.zones if z.unlocked) if state.zones else 0
        total_z  = len(state.zones) if state.zones else 0
        return {"ok": True, "output": (
            f"Tick: {state.tick} | IT Budget: {int(state.it_budget)} | "
            f"Suspicion: {round(state.suspicion, 1)}% | Patch: {'DEPLOYE' if state.patch_deployed else 'non deploye'}\n"
            f"Noeuds: {state.infected_count} infecte(s) | {state.quarantined_count} en quarantaine | "
            f"{state.healthy_count} sains | Zones accessibles: {unlocked}/{total_z}"
        )}

    if cmd == "audit":
        if not state.zones:
            return {"ok": True, "output": "Aucune zone definie."}
        lines = ["RAPPORT D'AUDIT RESEAU:"]
        for zone in state.zones:
            zone_nodes  = [n for n in state.nodes if n.zone_id == zone.id]
            infected    = sum(1 for n in zone_nodes if n.infected and not n.quarantined)
            quarantined = sum(1 for n in zone_nodes if n.quarantined)
            total       = len(zone_nodes)
            access      = "ACCES" if zone.unlocked else f"SEC.LVL {zone.security_level}"
            lines.append(
                f"  {zone.name:6} ({zone.label}): [{access}] "
                f"{infected}/{total} infectes, {quarantined} en quarantaine"
            )
        return {"ok": True, "output": "\n".join(lines)}

    if cmd == "scan":
        if _cd(state, "blue_scan") > 0:
            return {"ok": False, "output": f"[scan] Recharge — {_cd(state, 'blue_scan')} tick(s) restants."}
        result = apply_blue_action(state, {"action": "scan"})
        if result.get("ok"):
            _setcd(state, "blue_scan", 4)
            ids = result.get("infected_ids", [])
            if ids:
                return {"ok": True, "output": f"Scan termine. {len(ids)} noeud(s) infecte(s) — IDs: {ids}. IT: {result.get('it_budget')}"}
            return {"ok": True, "output": f"Scan termine. Reseau propre — aucun infecte detecte. IT: {result.get('it_budget')}"}
        return {"ok": False, "output": result.get("error", "Scan impossible.")}

    if cmd == "honeypot":
        if not args:
            return {"ok": False, "output": "Syntaxe: honeypot <node_id>"}
        try:
            node_id = int(args[0])
        except ValueError:
            return {"ok": False, "output": "L'identifiant de noeud doit etre un entier."}
        result = apply_blue_action(state, {"action": "honeypot", "node_id": node_id})
        if result.get("ok"):
            return {"ok": True, "output": f"Honeypot deploye sur noeud {node_id}. Piege actif. IT restant: {result.get('it_budget')}"}
        return {"ok": False, "output": result.get("error", "Honeypot impossible.")}

    if cmd == "quarantine":
        if not args:
            return {"ok": False, "output": "Syntaxe: quarantine <node_id>"}
        try:
            node_id = int(args[0])
        except ValueError:
            return {"ok": False, "output": "L'identifiant de noeud doit etre un entier."}
        result = apply_blue_action(state, {"action": "quarantine", "node_id": node_id})
        if result.get("ok"):
            return {"ok": True, "output": f"Noeud {node_id} isole en quarantaine. IT restant: {result.get('it_budget')}"}
        return {"ok": False, "output": result.get("error", "Quarantaine impossible.")}

    if cmd == "patch":
        result = apply_blue_action(state, {"action": "patch"})
        if result.get("ok"):
            return {"ok": True, "output": f"Patch de securite deploye. Le reseau commence a se nettoyer. IT restant: {result.get('it_budget')}"}
        return {"ok": False, "output": result.get("error", "Patch impossible.")}

    if cmd == "firewall":
        if not args:
            return {"ok": False, "output": "Syntaxe: firewall <node_id>"}
        try:
            node_id = int(args[0])
        except ValueError:
            return {"ok": False, "output": "L'identifiant de noeud doit etre un entier."}
        cost = 25
        if state.it_budget < cost:
            return {"ok": False, "output": f"IT insuffisant ({int(state.it_budget)}/{cost} requis)."}
        if not (0 <= node_id < len(state.nodes)):
            return {"ok": False, "output": f"Noeud {node_id} introuvable."}
        node = state.nodes[node_id]
        if node.infected or node.quarantined:
            return {"ok": False, "output": "Impossible de proteger un noeud infecte ou en quarantaine."}
        if node.honeypot:
            return {"ok": False, "output": "Ce noeud est deja protege."}
        node.honeypot = True
        state.it_budget -= cost
        state.firewalled_nodes[str(node_id)] = 10
        return {"ok": True, "output": f"Pare-feu active sur noeud {node_id} (10 ticks de protection). IT restant: {int(state.it_budget)}"}

    if cmd == "isolate":
        if not args:
            return {"ok": False, "output": "Syntaxe: isolate <zone> (DMZ, LAN, SRV, DB, SCADA)"}
        zone_name = args[0].upper()
        cost = 30
        if state.it_budget < cost:
            return {"ok": False, "output": f"IT insuffisant ({int(state.it_budget)}/{cost} requis)."}
        target_zone = next((z for z in (state.zones or []) if z.name == zone_name), None)
        if not target_zone:
            return {"ok": False, "output": f"Zone '{zone_name}' inconnue. Zones valides: DMZ, LAN, SRV, DB, SCADA"}
        infected_in_zone = [n for n in state.nodes if n.zone_id == target_zone.id and n.infected and not n.quarantined]
        if not infected_in_zone:
            return {"ok": False, "output": f"Aucun noeud infecte dans la zone {zone_name}."}
        for n in infected_in_zone:
            n.quarantined = True
        state.it_budget -= cost
        return {"ok": True, "output": f"Isolation complete: {len(infected_in_zone)} noeud(s) mis en quarantaine dans {zone_name}. IT restant: {int(state.it_budget)}"}

    if cmd == "analyze":
        if not args:
            return {"ok": False, "output": "Syntaxe: analyze <node_id>"}
        try:
            node_id = int(args[0])
        except ValueError:
            return {"ok": False, "output": "L'identifiant de noeud doit etre un entier."}
        if not (0 <= node_id < len(state.nodes)):
            return {"ok": False, "output": f"Noeud {node_id} introuvable."}
        node      = state.nodes[node_id]
        zone      = next((z for z in (state.zones or []) if z.id == node.zone_id), None)
        zone_name = zone.name if zone else "?"
        inf_nb    = [nid for nid in node.connections if state.nodes[nid].infected]
        status    = "INFECTE" if node.infected else ("QUARANTAINE" if node.quarantined else ("PROTEGE" if node.honeypot else "SAIN"))
        return {"ok": True, "output": (
            f"Noeud {node_id} | Zone: {zone_name} | Statut: {status} | Type: {'ROUTEUR' if node.is_router else 'WORKSTATION'}\n"
            f"Connexions: {len(node.connections)} | Voisins infectes: {len(inf_nb)} — {inf_nb}"
        )}

    if cmd == "log" and args and args[0].lower() == "suspicion":
        return {"ok": True, "output": f"Suspicion: {round(state.suspicion, 1)}%. Patch deploye: {bool(state.patch_deployed)}."}

    return {"ok": False, "output": f"Commande inconnue: {cmd}. Tapez 'help' pour la liste."}


# ── Upgrades ──────────────────────────────────────────────────────────

def buy_upgrade(state: GameState, upgrade_id: int) -> dict:
    """Achete une amelioration si le joueur a les ressources et respecte les prerequis de tier."""
    if upgrade_id in state.purchased_upgrades:
        return {"ok": False, "error": "Amelioration deja achetee."}

    upgrades = get_all_upgrades()
    upgrade  = next((u for u in upgrades if u["id"] == upgrade_id), None)
    if not upgrade:
        return {"ok": False, "error": "Amelioration inconnue."}

    allowed = upgrade["effect_json"].get("allowed_malware")
    if allowed and state.malware_class not in allowed:
        return {"ok": False, "error": "Cette amelioration n'est pas compatible avec votre malware."}

    if state.cpu_cycles < upgrade["cost"]:
        return {"ok": False, "error": f"Pas assez de CPU Cycles ({upgrade['cost']} requis)."}

    if upgrade["tier"] > 1:
        same_branch = [u for u in upgrades
                       if u["branch"] == upgrade["branch"]
                       and u["tier"] == upgrade["tier"] - 1
                       and (not u["effect_json"].get("allowed_malware")
                            or state.malware_class in u["effect_json"]["allowed_malware"])]
        if same_branch and not any(u["id"] in state.purchased_upgrades for u in same_branch):
            return {"ok": False, "error": "Vous devez d'abord acheter l'amelioration precedente."}

    state.cpu_cycles -= upgrade["cost"]
    state.purchased_upgrades.append(upgrade_id)

    effect = upgrade["effect_json"]
    if "propagation_bonus" in effect:
        state.propagation_mod      += effect["propagation_bonus"]
    if "stealth" in effect:
        state.stealth_mod          += effect["stealth"]
    if "income_bonus" in effect:
        state.income_mod           += effect["income_bonus"]
    if "passive_income" in effect:
        state.passive_income_bonus += effect["passive_income"]
    
    # Bonus spécial pour le craquage de routeurs (protection bypass)
    # Les modules de branche "transmission" donnent un bonus cumulatif important (+10%)
    if upgrade["branch"] == "transmission":
        if not hasattr(state, 'router_crack_bonus'):
            state.router_crack_bonus = 0.0
        state.router_crack_bonus += 0.10

    # Bonus spécial pour la réduction de méfiance passive
    if "suspicion_reduction" in effect:
        if not hasattr(state, 'passive_stealth_reduction'):
            state.passive_stealth_reduction = 0.0
        state.passive_stealth_reduction += effect["suspicion_reduction"]

    # Réduction immédiate de suspicion
    if "immediate_suspicion_cut" in effect:
        state.suspicion = max(0.0, state.suspicion - effect["immediate_suspicion_cut"])

    state.stealth_mod += upgrade.get("stealth_mod", 0)

    return {"ok": True, "upgrade": upgrade["name"], "remaining_cycles": round(state.cpu_cycles, 1)}
