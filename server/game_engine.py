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

    n_inf = m_inf * (t_inf + m_mod) * ratio * propagation_mult
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
                        # Zone verrouillée : seul le routeur peut être attaqué
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
        adjusted    = base_chance * (1.0 + state.propagation_mod) * propagation_mult
        if random.random() < adjusted:
            router.infected = True

    # Déverrouillage des zones dont le routeur vient d'être infecté
    for zone in (state.zones or []):
        if not zone.unlocked and zone.router_id is not None:
            if state.nodes[zone.router_id].infected:
                zone.unlocked = True

    # Revenus Red Team
    income = profile["income_per_node"]
    state.cpu_cycles += state.infected_count * (income + state.income_mod) * 0.15 * income_mult
    state.cpu_cycles += state.passive_income_bonus

    # Budget Blue Team (régénération passive)
    state.it_budget += state.healthy_count * 0.3

    # Bruit et méfiance
    b_machine          = profile["noise_per_machine"]
    stealth_factor     = max(0.05, 1.0 - state.stealth_mod)
    b_total            = state.infected_count * b_machine * stealth_factor
    suspicion_increase = b_total * 0.12 * suspicion_mult
    state.suspicion    = min(100.0, state.suspicion + suspicion_increase)

    # Événements Blue Team automatiques
    blue_events = get_blueteam_events()
    for event in blue_events:
        if state.suspicion >= event["trigger_threshold"]:
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
            x = round(anc.x + random.uniform(-50, 50), 1)
            y = round(anc.y + random.uniform(-50, 50), 1)
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


def execute_command(state: GameState, line: str) -> dict:
    """Interprete une ligne de commande du terminal (Red Team uniquement)."""
    raw = (line or "").strip()
    if not raw:
        return {"ok": False, "output": "Aucune commande saisie."}

    if raw == "-niter cheagger":
        state.cpu_cycles = 99999
        return {"ok": True, "output": "[OVERRIDE] CPU Cycles -> 99 999. Budget illimite."}

    tokens = raw.split()
    cmd    = tokens[0].lower()
    args   = tokens[1:]

    if cmd in ("help", "aide", "?"):
        mc = state.malware_class

        common_commands = [
            ("help",              "Affiche cette aide."),
            ("status",            "Resume de l'etat du malware."),
            ("zones",             "Affiche l'etat de toutes les zones reseau."),
            ("hack",              "Active la capacite speciale de votre classe (cooldown variable)."),
            ("nmap -A -sV",       "Scan agressif du reseau (+10 CPU, cd 6t)."),
            ("nmap -sS -T4 -Pn",  "Scan SYN furtif, reduit la mefiance (cd 8t)."),
            ("phishing start",    "Lance une campagne de phishing (cd 10t)."),
            ("log suspicion",     "Affiche la jauge de mefiance actuelle."),
            ("ifconfig",          "Affiche les infos reseau de la session."),
            ("whoami",            "Affiche votre identite malware."),
            ("ps aux",            "Liste les processus actifs (cd 6t)."),
            ("cat /etc/shadow",   "Tente une extraction de hash (cd 12t)."),
            ("tcpdump -i eth0 -nn","Capture du trafic reseau (cd 10t)."),
        ]

        malware_commands = {
            "worm": [
                ("masscan --rate 10000 -p0-65535", "Scan massif de ports (cd 10t)."),
                ("exploit/ms17-010",               "Lance l'exploit EternalBlue (cd 15t)."),
                ("./propagate --aggressive",        "Force la propagation (cd 12t)."),
                ("botnet deploy <miners|ddos>",     "Deploie le botnet (cd 15/20t)."),
            ],
            "trojan": [
                ("msfvenom -p reverse_tcp",             "Genere un payload reverse shell (cd 10t)."),
                ("mimikatz sekurlsa::logonpasswords",    "Dump les credentials (cd 12t)."),
                ("ssh -D 1080 pivot@target",             "Ouvre un tunnel SOCKS (cd 10t)."),
                ("exfil --dns --encode base64",          "Exfiltration DNS furtive (cd 12t)."),
            ],
            "ransomware": [
                ("encrypt --cipher aes-256-cbc", "Chiffre les fichiers (cd 12t)."),
                ("ransom --note DROP",            "Depose une demande de rancon (cd 10t)."),
                ("wmic shadowcopy delete",        "Supprime les sauvegardes (cd 15t)."),
                ("tor-negotiate --btc-wallet",    "Negocie paiement via Tor (cd 20t)."),
            ],
            "rootkit": [
                ("insmod /dev/null/rootkit.ko",      "Injecte un module noyau (cd 12t)."),
                ("syscall_hook --hide-pid",          "Hook les appels systeme (cd 15t)."),
                ("dd if=/dev/sda bs=512 count=1",    "Infecte le bootloader (cd 15t)."),
                ("ld_preload inject /lib/libhook.so","Injection via LD_PRELOAD (cd 12t)."),
            ],
        }

        all_rows  = common_commands + malware_commands.get(mc, [])
        cmd_width = max(len(name) for name, _ in all_rows) if all_rows else 20

        rows = [f"{name.ljust(cmd_width)} - {desc}" for name, desc in common_commands]
        rows.append("")
        rows.append(f"[{mc.upper()}]")
        rows.extend(f"{name.ljust(cmd_width)} - {desc}" for name, desc in malware_commands.get(mc, []))

        title       = "AVAILABLE COMMANDS"
        inner_width = max(len(title), *(len(r) for r in rows))
        sep         = "+" + "-" * (inner_width + 2) + "+"
        boxed       = [sep, f"| {title.ljust(inner_width)} |", sep]
        boxed      += [f"| {r.ljust(inner_width)} |" for r in rows]
        boxed.append(sep)
        return {"ok": True, "output": "\n".join(boxed)}

    if cmd in ("status", "statut"):
        hack_str  = "PRET" if state.special_cooldown == 0 else f"recharge ({state.special_cooldown} ticks)"
        zones_str = ""
        if state.zones:
            unlocked = sum(1 for z in state.zones if z.unlocked)
            zones_str = f" | Zones: {unlocked}/{len(state.zones)} debloquees"
        return {"ok": True, "output": (
            f"Tick: {state.tick} | Malware: {state.malware_class} | "
            f"Noeuds infectes: {state.infected_count}/{state.total_nodes} | "
            f"CPU: {int(state.cpu_cycles)} | Mefiance: {round(state.suspicion, 1)}%"
            f" | Hack: {hack_str}{zones_str}"
        )}

    if cmd == "zones":
        if not state.zones:
            return {"ok": True, "output": "Aucune zone définie."}
        lines = ["ZONES RESEAU:"]
        for zone in state.zones:
            zone_nodes = [n for n in state.nodes if n.zone_id == zone.id]
            infected   = sum(1 for n in zone_nodes if n.infected and not n.quarantined)
            total      = len(zone_nodes)
            if zone.unlocked:
                status = f"DEBLOQUE  [{infected}/{total} infectes]"
            else:
                status = f"VERROUILLE (SEC.LVL {zone.security_level})"
                if zone.router_id is not None:
                    rtr = state.nodes[zone.router_id]
                    rtr_status = "INFECTE" if rtr.infected else "protege"
                    chance = round(ROUTER_INFECTION_CHANCE.get(zone.security_level, 0.05) * 100, 1)
                    status += f" — routeur: {rtr_status} (~{chance}%/tick)"
            lines.append(f"  [{zone.name}] {zone.label} — {status}")
        return {"ok": True, "output": "\n".join(lines)}

    if cmd in ("nmap", "scan"):
        flags = " ".join(args)
        if "-sS" in flags and "-T4" in flags and "-Pn" in flags:
            if _cd(state, "nmap_stealth") > 0:
                return {"ok": False, "output": f"[nmap furtif] Recharge — {_cd(state, 'nmap_stealth')} tick(s) restants."}
            state.cpu_cycles += 8
            state.suspicion   = max(0, state.suspicion - 2.0)
            _setcd(state, "nmap_stealth", 8)
            return {"ok": True, "output": "Scan SYN furtif termine. Reseau cartographie sans alerter l'IDS. (+8 CPU, mefiance -2%)"}
        bonus = 5
        if "-A" in flags and "-sV" in flags:
            if _cd(state, "nmap_aggr") > 0:
                return {"ok": False, "output": f"[nmap] Recharge — {_cd(state, 'nmap_aggr')} tick(s) restants."}
            bonus = 10
            _setcd(state, "nmap_aggr", 6)
        state.cpu_cycles += bonus
        return {"ok": True, "output": f"Scan reseau termine ({flags or 'mode par defaut'}). Nouvelles surfaces identifiees (+{bonus} CPU Cycles)."}

    if cmd == "ifconfig":
        return {"ok": True, "output": (
            f"eth0: inet 10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}  "
            f"netmask 255.255.0.0  broadcast 10.255.255.255\n"
            f"  Noeuds actifs: {state.total_nodes} | Infectes: {state.infected_count} | "
            f"Interfaces compromises: {min(state.infected_count, 8)}"
        )}

    if cmd == "whoami":
        names = {"worm": "w0rm_Agent", "trojan": "tr0jan_H0rse", "ransomware": "ransom_L0ck", "rootkit": "r00t_gh0st"}
        return {"ok": True, "output": (
            f"uid=0(root) gid=0(root) groups=0(root)\n"
            f"Identite malware: {names.get(state.malware_class, 'unknown')} [{state.malware_class.upper()}]\n"
            f"Tick actif: {state.tick} | Score: {state.score}"
        )}

    if cmd == "ps" and args and args[0].lower() == "aux":
        if _cd(state, "ps_aux") > 0:
            return {"ok": False, "output": f"[ps aux] Recharge — {_cd(state, 'ps_aux')} tick(s) restants."}
        state.cpu_cycles += 3
        procs = [
            "root       1  0.0  sshd: /usr/sbin/sshd",
            f"root     666  {round(state.suspicion/10,1)}  [malware/{state.malware_class}]",
            f"root     667  0.{random.randint(1,9)}  [c2_beacon]",
        ]
        if state.infected_count > 5:
            procs.append(f"root     668  1.2  [propagation_thread x{state.infected_count}]")
        _setcd(state, "ps_aux", 6)
        return {"ok": True, "output": "USER     PID  %CPU  COMMAND\n" + "\n".join(procs) + "\n(+3 CPU)"}

    if raw.lower().startswith("cat /etc/shadow"):
        if _cd(state, "shadow") > 0:
            return {"ok": False, "output": f"[shadow] Recharge — {_cd(state, 'shadow')} tick(s) restants."}
        state.cpu_cycles += 15
        state.suspicion   = min(100, state.suspicion + 1.5)
        hashes = [
            "root:$6$rNd0m$K8x9zLqV3mH7wP2jF5nG1bYcT4vA6dR0eI8uQ3sW7kJ:19458:0:99999:7:::",
            "admin:$6$S4lt3d$Fp2xR7mN1qL9wK3jH6gT8bYcU5vA0dE2oI4uQ7sW3kJ:19458:0:99999:7:::",
        ]
        _setcd(state, "shadow", 12)
        return {"ok": True, "output": "\n".join(hashes) + "\nHash extraits avec succes. (+15 CPU, mefiance +1.5%)"}

    if cmd == "tcpdump":
        flags = " ".join(args)
        if "-i" in flags and "-nn" in flags:
            if _cd(state, "tcpdump") > 0:
                return {"ok": False, "output": f"[tcpdump] Recharge — {_cd(state, 'tcpdump')} tick(s) restants."}
            state.cpu_cycles += 12
            _setcd(state, "tcpdump", 10)
            return {"ok": True, "output": (
                f"tcpdump: listening on eth0, link-type EN10MB\n"
                f"  {state.infected_count * 47} packets captured\n"
                f"  {state.infected_count * 3} packets with credentials detected\n"
                f"Trafic intercepte avec succes. (+12 CPU)"
            )}
        return {"ok": False, "output": "Syntaxe: tcpdump -i eth0 -nn"}

    if cmd == "phishing" and args and args[0].lower() == "start":
        if _cd(state, "phishing") > 0:
            return {"ok": False, "output": f"[phishing] Recharge — {_cd(state, 'phishing')} tick(s) restants."}
        gain = max(8, int(state.infected_count * 1.5) or 8)
        state.cpu_cycles += gain
        _setcd(state, "phishing", 10)
        return {"ok": True, "output": f"Campagne de phishing lancee. Plusieurs utilisateurs ont clique... (+{gain} CPU Cycles)"}

    if state.malware_class == "worm":
        if cmd == "masscan" and "--rate" in " ".join(args) and "-p0-65535" in " ".join(args):
            if _cd(state, "masscan") > 0:
                return {"ok": False, "output": f"[masscan] Recharge — {_cd(state, 'masscan')} tick(s) restants."}
            state.cpu_cycles += 25
            state.suspicion   = min(100, state.suspicion + 3.0)
            _setcd(state, "masscan", 10)
            return {"ok": True, "output": (
                f"Masscan: scanned {state.total_nodes * 65535} ports in 2.31s\n"
                f"  {random.randint(12, 30)} services vulnerables identifies.\n"
                f"  Surfaces d'attaque maximisees. (+25 CPU, mefiance +3%)"
            )}

        if raw.lower().startswith("exploit/ms17-010"):
            if _cd(state, "ms17") > 0:
                return {"ok": False, "output": f"[exploit] Recharge — {_cd(state, 'ms17')} tick(s) restants."}
            state.cpu_cycles += 20
            state.suspicion   = min(100, state.suspicion + 4.0)
            candidates = _unlocked_candidates(state)
            extra = 0
            if candidates:
                for n in random.sample(candidates, min(2, len(candidates))):
                    n.infected = True
                    extra += 1
            _setcd(state, "ms17", 15)
            return {"ok": True, "output": (
                f"[*] Exploit EternalBlue (MS17-010) lance...\n"
                f"[+] {extra} noeud(s) infecte(s) dans les zones accessibles. (+20 CPU, mefiance +4%)"
            )}

        if raw.lower().startswith("./propagate") and "--aggressive" in raw.lower():
            if _cd(state, "propagate") > 0:
                return {"ok": False, "output": f"[propagate] Recharge — {_cd(state, 'propagate')} tick(s) restants."}
            state.cpu_cycles += 18
            state.suspicion   = min(100, state.suspicion + 2.5)
            _setcd(state, "propagate", 12)
            return {"ok": True, "output": f"Propagation agressive activee sur {state.infected_count} hotes. (+18 CPU, mefiance +2.5%)"}

        if cmd == "botnet" and args and args[0].lower() == "deploy" and len(args) >= 2:
            subtype = args[1].lower()
            if subtype == "miners":
                if _cd(state, "botnet_miners") > 0:
                    return {"ok": False, "output": f"[botnet miners] Recharge — {_cd(state, 'botnet_miners')} tick(s) restants."}
                state.cpu_cycles += 30
                state.suspicion   = min(100, state.suspicion + 2.0)
                _setcd(state, "botnet_miners", 15)
                return {"ok": True, "output": f"Botnet mining deploye sur {state.infected_count} machines. Hashrate: {state.infected_count * 12.5} MH/s (+30 CPU, mefiance +2%)"}
            if subtype == "ddos":
                if _cd(state, "botnet_ddos") > 0:
                    return {"ok": False, "output": f"[botnet ddos] Recharge — {_cd(state, 'botnet_ddos')} tick(s) restants."}
                state.cpu_cycles += 35
                state.suspicion   = min(100, state.suspicion + 5.0)
                _setcd(state, "botnet_ddos", 20)
                return {"ok": True, "output": f"Attaque DDoS lancee depuis {state.infected_count} bots. Debit: {state.infected_count * 2.5} Gbps. (+35 CPU, mefiance +5%)"}
        if cmd == "botnet":
            return {"ok": False, "output": "Syntaxe: botnet deploy <miners|ddos>"}

    if state.malware_class == "trojan":
        if cmd == "msfvenom" and "-p" in " ".join(args) and "reverse_tcp" in " ".join(args):
            if _cd(state, "msfvenom") > 0:
                return {"ok": False, "output": f"[msfvenom] Recharge — {_cd(state, 'msfvenom')} tick(s) restants."}
            state.cpu_cycles += 20
            _setcd(state, "msfvenom", 10)
            return {"ok": True, "output": (
                f"Payload genere: windows/meterpreter/reverse_tcp\n"
                f"  LHOST=10.0.0.{random.randint(1,254)} LPORT=4444\n"
                f"  Taille: {random.randint(350,500)} bytes. Encodage shikata_ga_nai x3. (+20 CPU)"
            )}

        if cmd == "mimikatz" and args and "sekurlsa::logonpasswords" in args[0].lower():
            if _cd(state, "mimikatz") > 0:
                return {"ok": False, "output": f"[mimikatz] Recharge — {_cd(state, 'mimikatz')} tick(s) restants."}
            state.cpu_cycles += 25
            _setcd(state, "mimikatz", 12)
            return {"ok": True, "output": (
                f"mimikatz # sekurlsa::logonpasswords\n"
                f"  User: Administrator | NTLM: {'{:032x}'.format(random.getrandbits(128))}\n"
                f"  {random.randint(3, 8)} credentials extraits silencieusement. (+25 CPU)"
            )}

        if cmd == "ssh" and "-D" in " ".join(args) and "1080" in " ".join(args):
            if _cd(state, "ssh_tunnel") > 0:
                return {"ok": False, "output": f"[ssh tunnel] Recharge — {_cd(state, 'ssh_tunnel')} tick(s) restants."}
            state.cpu_cycles += 18
            _setcd(state, "ssh_tunnel", 10)
            return {"ok": True, "output": f"Tunnel SOCKS5 ouvert sur 127.0.0.1:1080. Pivot actif via {state.infected_count} noeuds. (+18 CPU)"}

        if cmd == "exfil" and "--dns" in " ".join(args) and "base64" in " ".join(args):
            if _cd(state, "exfil") > 0:
                return {"ok": False, "output": f"[exfil] Recharge — {_cd(state, 'exfil')} tick(s) restants."}
            state.cpu_cycles += 30
            state.suspicion   = max(0, state.suspicion - 1.5)
            _setcd(state, "exfil", 12)
            return {"ok": True, "output": f"Exfiltration DNS: {random.randint(50, 200)} Ko exfiltres via dns.tunnel.corp. Aucune alerte IDS. (+30 CPU, mefiance -1.5%)"}

    if state.malware_class == "ransomware":
        if cmd == "encrypt" and "--cipher" in " ".join(args) and "aes-256-cbc" in " ".join(args):
            if _cd(state, "encrypt") > 0:
                return {"ok": False, "output": f"[encrypt] Recharge — {_cd(state, 'encrypt')} tick(s) restants."}
            state.cpu_cycles += 25
            state.suspicion   = min(100, state.suspicion + 4.0)
            _setcd(state, "encrypt", 12)
            return {"ok": True, "output": f"Chiffrement AES-256-CBC: {state.infected_count * random.randint(800, 2000)} fichiers chiffres. (+25 CPU, mefiance +4%)"}

        if cmd == "ransom" and "--note" in " ".join(args) and "DROP" in raw:
            if _cd(state, "ransom_note") > 0:
                return {"ok": False, "output": f"[ransom] Recharge — {_cd(state, 'ransom_note')} tick(s) restants."}
            state.cpu_cycles += 20
            state.suspicion   = min(100, state.suspicion + 2.0)
            _setcd(state, "ransom_note", 10)
            return {"ok": True, "output": f"Note de rancon deposee sur {state.infected_count} machines. READ_ME.txt cree. (+20 CPU, mefiance +2%)"}

        if cmd == "wmic" and "shadowcopy" in " ".join(args).lower() and "delete" in " ".join(args).lower():
            if _cd(state, "wmic") > 0:
                return {"ok": False, "output": f"[wmic] Recharge — {_cd(state, 'wmic')} tick(s) restants."}
            state.cpu_cycles += 22
            state.suspicion   = min(100, state.suspicion + 3.5)
            _setcd(state, "wmic", 15)
            return {"ok": True, "output": f"Suppression des Volume Shadow Copies: {random.randint(5, 15)} points detruits. (+22 CPU, mefiance +3.5%)"}

        if raw.lower().startswith("tor-negotiate") and "--btc-wallet" in raw.lower():
            if _cd(state, "tor_negotiate") > 0:
                return {"ok": False, "output": f"[tor-negotiate] Recharge — {_cd(state, 'tor_negotiate')} tick(s) restants."}
            state.cpu_cycles += 35
            state.suspicion   = min(100, state.suspicion + 1.0)
            _setcd(state, "tor_negotiate", 20)
            return {"ok": True, "output": f"Connexion Tor etablie. Wallet: bc1q{'{:040x}'.format(random.getrandbits(160))[:40]}. Paiement partiel recu. (+35 CPU, mefiance +1%)"}

    if state.malware_class == "rootkit":
        if cmd == "insmod" and "/dev/null/rootkit.ko" in raw:
            if _cd(state, "insmod") > 0:
                return {"ok": False, "output": f"[insmod] Recharge — {_cd(state, 'insmod')} tick(s) restants."}
            state.cpu_cycles += 20
            state.suspicion   = max(0, state.suspicion - 2.0)
            _setcd(state, "insmod", 12)
            return {"ok": True, "output": "Module noyau injecte: rootkit.ko. Hooks sys_read/sys_write/getdents64 installes. (+20 CPU, mefiance -2%)"}

        if cmd == "syscall_hook" and "--hide-pid" in raw.lower():
            if _cd(state, "syscall_hook") > 0:
                return {"ok": False, "output": f"[syscall_hook] Recharge — {_cd(state, 'syscall_hook')} tick(s) restants."}
            state.cpu_cycles += 25
            state.suspicion   = max(0, state.suspicion - 3.0)
            _setcd(state, "syscall_hook", 15)
            return {"ok": True, "output": "Hooks syscall installes. PID masque dans /proc. Invisible pour ps/top/htop. (+25 CPU, mefiance -3%)"}

        if cmd == "dd" and "/dev/sda" in raw and "bs=512" in " ".join(args) and "count=1" in " ".join(args):
            if _cd(state, "dd_mbr") > 0:
                return {"ok": False, "output": f"[dd] Recharge — {_cd(state, 'dd_mbr')} tick(s) restants."}
            state.cpu_cycles += 22
            state.suspicion   = min(100, state.suspicion + 1.0)
            _setcd(state, "dd_mbr", 15)
            return {"ok": True, "output": "MBR/UEFI infecte. Persistance maximale : survit au reformatage. (+22 CPU, mefiance +1%)"}

        if cmd == "ld_preload" and "inject" in raw.lower() and "/lib/libhook.so" in raw:
            if _cd(state, "ld_preload") > 0:
                return {"ok": False, "output": f"[ld_preload] Recharge — {_cd(state, 'ld_preload')} tick(s) restants."}
            state.cpu_cycles += 30
            state.suspicion   = max(0, state.suspicion - 2.5)
            _setcd(state, "ld_preload", 12)
            return {"ok": True, "output": "LD_PRELOAD injection reussie /lib/libhook.so. Toutes les fonctions libc interceptees. (+30 CPU, mefiance -2.5%)"}

    if cmd in ("hack", "special", "ability"):
        if state.special_cooldown > 0:
            return {"ok": False, "output": f"Hack special en recharge... ({state.special_cooldown} ticks restants)"}

        if state.malware_class == "worm":
            candidates = _unlocked_candidates(state)
            targets    = random.sample(candidates, min(4, len(candidates)))
            for n in targets:
                n.infected = True
            state.special_cooldown = 15
            state.suspicion        = min(100.0, state.suspicion + 5.0)
            return {"ok": True, "output": f"[WORM] Propagation de masse : {len(targets)} noeud(s) infecte(s) dans les zones accessibles. (mefiance +5%, cooldown: 15)"}

        if state.malware_class == "trojan":
            reduction              = round(min(state.suspicion, 25.0), 1)
            state.suspicion        = max(0.0, state.suspicion - reduction)
            state.special_cooldown = 20
            return {"ok": True, "output": f"[TROJAN] Mode fantome : traces effacees. Mefiance -{reduction}%. (cooldown: 20)"}

        if state.malware_class == "ransomware":
            state.cpu_cycles      += 200
            state.suspicion        = min(100.0, state.suspicion + 8.0)
            state.special_cooldown = 25
            return {"ok": True, "output": "[RANSOMWARE] Paiement force via crypto-mixer. +200 CPU. (mefiance +8%, cooldown: 25)"}

        if state.malware_class == "rootkit":
            old_sus                = round(state.suspicion, 1)
            state.suspicion        = 0.0
            state.special_cooldown = 30
            return {"ok": True, "output": f"[ROOTKIT] Zero-trace : tous les logs effaces. Mefiance {old_sus}% -> 0%. (cooldown: 30)"}

        return {"ok": False, "output": "Classe de malware inconnue."}

    if cmd == "upgrade":
        if not args:
            return {"ok": False, "output": "Syntaxe: upgrade <nom_amelioration>"}
        target   = " ".join(args).lower()
        upgrades = get_all_upgrades()
        found    = None
        for u in upgrades:
            allowed = u["effect_json"].get("allowed_malware", [])
            if allowed and state.malware_class not in allowed:
                continue
            if target in u["name"].lower():
                found = u
                break
        if not found:
            return {"ok": False, "output": f"Aucune amelioration correspondant a '{target}' pour {state.malware_class}."}
        result = buy_upgrade(state, found["id"])
        if result.get("ok"):
            return {"ok": True, "output": f"Amelioration '{found['name']}' installee. CPU restants: {result['remaining_cycles']}."}
        return {"ok": False, "output": result.get("error", "Achat impossible.")}

    if cmd == "log" and args and args[0].lower() == "suspicion":
        return {"ok": True, "output": f"Mefiance: {round(state.suspicion, 1)}%. Patch deploye: {bool(state.patch_deployed)}."}

    return {"ok": False, "output": f"Commande inconnue: {cmd}. Tapez 'help' pour la liste."}


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
    state.stealth_mod += upgrade.get("stealth_mod", 0)

    return {"ok": True, "upgrade": upgrade["name"], "remaining_cycles": round(state.cpu_cycles, 1)}
