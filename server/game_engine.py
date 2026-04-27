"""
Moteur de jeu BLACKOUT — exécute la logique de chaque tick.

Algorithmes du cahier des charges :
  Propagation : N_inf = M_inf × (T_inf + M_mod) × (M_saines / M_totales) × diff_mult
  Bruit       : B_total = M_inf × B_machine
  Défense     : M_inf(t) = M_inf(t-1) + N_inf − M_nettoyees

Économie cible (difficulté normale, ~150 ticks) :
  Passif  : ~90  CPU  (income_per_node * 0.05 * avg_infected)
  Bulles  : ~60  CPU  (spawn 8%, valeur 4-10)
  Cmds    : ~80  CPU  (cooldowns 6-20 ticks, bonus réduits)
  Total   : ~280 CPU + 50 de départ = ~330 CPU pour la partie
  → permet d'acheter 4-5 upgrades, pas la totalité de l'arbre
"""

import random
import json
from server.game_state import GameState, Bubble, MALWARE_PROFILES
from server.database import get_all_upgrades, get_blueteam_events


def process_tick(state: GameState) -> GameState:
    """Avance l'état de jeu d'un tick. Retourne l'état modifié."""
    if state.result is not None:
        return state

    state.tick += 1
    if state.special_cooldown > 0:
        state.special_cooldown -= 1

    # Décrémenter les cooldowns de commandes terminal
    for key in list(state.command_cooldowns.keys()):
        if state.command_cooldowns[key] > 0:
            state.command_cooldowns[key] -= 1

    profile = MALWARE_PROFILES[state.malware_class]

    m_inf = state.infected_count
    m_saines = state.healthy_count
    m_totales = state.total_nodes

    if m_totales == 0:
        return state

    # ── Modificateurs de difficulté ──────────────────────────────
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
    else:  # normal
        suspicion_mult        = 1.00
        income_mult           = 1.00
        propagation_mult      = 1.00
        difficulty_clean_rate = 0.18

    # ── 1. Propagation ───────────────────────────────────────────
    t_inf = profile["propagation"]
    m_mod = state.propagation_mod
    ratio = m_saines / m_totales if m_totales > 0 else 0

    n_inf = m_inf * (t_inf + m_mod) * ratio * propagation_mult
    # Arrondi probabiliste : évite que round(0.37) = 0 bloque la progression
    whole = int(n_inf)
    frac = n_inf - whole
    new_infections = whole + (1 if random.random() < frac else 0)

    candidates = set()
    for node in state.nodes:
        if node.infected and not node.quarantined:
            for neighbor_id in node.connections:
                neighbor = state.nodes[neighbor_id]
                if not neighbor.infected and not neighbor.quarantined and not neighbor.honeypot:
                    candidates.add(neighbor_id)

    if candidates and new_infections > 0:
        to_infect = random.sample(list(candidates), min(new_infections, len(candidates)))
        for nid in to_infect:
            state.nodes[nid].infected = True

    # ── 2. Revenus ───────────────────────────────────────────────
    # Multiplicateur 0.05 : chaque nœud infecté rapporte très peu — les
    # upgrades et commandes doivent être des choix délibérés, pas des acquis.
    income = profile["income_per_node"]
    state.cpu_cycles += state.infected_count * (income + state.income_mod) * 0.05 * income_mult
    state.cpu_cycles += state.passive_income_bonus

    state.it_budget += state.healthy_count * 0.3

    # ── 3. Bruit & Méfiance ─────────────────────────────────────
    b_machine = profile["noise_per_machine"]
    stealth_factor = max(0.05, 1.0 - state.stealth_mod)
    b_total = state.infected_count * b_machine * stealth_factor

    suspicion_increase = b_total * 0.12 * suspicion_mult
    state.suspicion = min(100.0, state.suspicion + suspicion_increase)

    # ── 4. Événements Blue Team ──────────────────────────────────
    blue_events = get_blueteam_events()
    for event in blue_events:
        if state.suspicion >= event["trigger_threshold"]:
            effect = event["effect_json"]
            eid = event["id"]
            already_triggered = eid in state.triggered_events

            if effect.get("trap_node") and not any(n.honeypot for n in state.nodes):
                healthy_nodes = [n for n in state.nodes if not n.infected and not n.quarantined]
                if healthy_nodes:
                    trap = random.choice(healthy_nodes)
                    trap.honeypot = True

            if effect.get("quarantine") and (state.tick - state.quarantine_last_tick) >= 10:
                infected_nodes = [n for n in state.nodes if n.infected and not n.quarantined]
                if infected_nodes:
                    iso_count = max(1, int(len(infected_nodes) * effect.get("isolation_rate", 0.1)))
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

    # ── 5. Patch de sécurité (méfiance = 100%) ──────────────────
    if state.suspicion >= 100.0 and not state.patch_deployed:
        state.patch_deployed = True
        state.clean_rate = difficulty_clean_rate

    if state.patch_deployed:
        m_nettoyees = max(1, round(state.infected_count * state.clean_rate))
        infected_list = [n for n in state.nodes if n.infected and not n.quarantined]
        if infected_list:
            to_clean = random.sample(infected_list, min(m_nettoyees, len(infected_list)))
            for node in to_clean:
                node.infected = False

    # ── 6. Génération de bulles ──────────────────────────────────
    _spawn_bubbles(state)

    state.bubbles = [b for b in state.bubbles if b.ttl > 0]
    for b in state.bubbles:
        b.ttl -= 1

    # ── 7. Score ─────────────────────────────────────────────────
    state.score = state.tick * 10 + state.infected_count * 5

    # ── 8. Conditions de fin ─────────────────────────────────────
    if state.healthy_count == 0 and state.quarantined_count == 0:
        state.result = "victory"
        state.score += 1000
    elif state.infected_count == 0:
        state.result = "defeat"

    return state


def _spawn_bubbles(state: GameState):
    """Fait apparaître des bulles cliquables aléatoirement.
    Probabilités et valeurs basses pour que les bulles soient un bonus,
    pas une source de revenu principale.
    """
    if random.random() < 0.08:
        kind = random.choice(["breach", "exfiltration"])
        value = random.randint(4, 10)
        x = random.uniform(50, 850)
        y = random.uniform(50, 650)
        state.bubbles.append(Bubble(
            id=state.next_bubble_id, x=round(x, 1), y=round(y, 1),
            kind=kind, value=value, ttl=5,
        ))
        state.next_bubble_id += 1

    if random.random() < 0.06:
        kind = random.choice(["log_analysis", "patch_deploy"])
        value = random.randint(2, 8)
        x = random.uniform(50, 850)
        y = random.uniform(50, 650)
        state.bubbles.append(Bubble(
            id=state.next_bubble_id, x=round(x, 1), y=round(y, 1),
            kind=kind, value=value, ttl=5,
        ))
        state.next_bubble_id += 1


def click_bubble(state: GameState, bubble_id: int) -> dict:
    """Traite le clic sur une bulle. Retourne un feedback."""
    for i, b in enumerate(state.bubbles):
        if b.id == bubble_id:
            if b.kind in ("breach", "exfiltration"):
                state.cpu_cycles += b.value
                feedback = {"type": "attacker", "kind": b.kind, "gained": b.value}
            else:
                suspicion_delta = b.value * 0.35
                state.suspicion = min(100.0, state.suspicion + suspicion_delta)
                feedback = {"type": "defender", "kind": b.kind, "suspicion_added": suspicion_delta}
            state.bubbles.pop(i)
            return feedback
    return {"error": "Bulle introuvable."}


# ── Helpers cooldown terminal ─────────────────────────────────────────

def _cd(state: GameState, key: str) -> int:
    return state.command_cooldowns.get(key, 0)


def _setcd(state: GameState, key: str, ticks: int):
    state.command_cooldowns[key] = ticks


def execute_command(state: GameState, line: str) -> dict:
    """
    Interprète une ligne de commande du terminal.
    Chaque commande à récompense a un cooldown pour empêcher le farming.
    Les bonus sont volontairement bas — les commandes complètent l'économie,
    elles ne la dominent pas.
    """
    raw = (line or "").strip()
    if not raw:
        return {"ok": False, "output": "Aucune commande saisie."}

    # ── Cheat code caché ─────────────────────────────────────────
    if raw == "-niter cheagger":
        state.cpu_cycles = 99999
        return {
            "ok": True,
            "output": "💀 ░░ OVERRIDE ACCEPTED ░░ CPU Cycles → 99 999.",
        }

    tokens = raw.split()
    cmd = tokens[0].lower()
    args = tokens[1:]

    # Aide
    if cmd in ("help", "aide", "?"):
        mc = state.malware_class

        common_commands = [
            ("help", "Affiche cette aide."),
            ("status", "Resume de l'etat du malware."),
            ("hack", "Active la capacite speciale de votre classe (cooldown variable)."),
            ("nmap -A -sV", "Scan agressif (+6 CPU, cd 6t)."),
            ("nmap -sS -T4 -Pn", "Scan furtif, reduit la mefiance (cd 8t)."),
            ("phishing start", "Campagne de phishing (cd 10t)."),
            ("log suspicion", "Affiche la jauge de mefiance actuelle."),
            ("ifconfig", "Infos reseau de la session."),
            ("whoami", "Identite malware."),
            ("ps aux", "Liste les processus actifs (cd 6t)."),
            ("cat /etc/shadow", "Extraction de hash (cd 12t)."),
            ("tcpdump -i eth0 -nn", "Capture trafic reseau (cd 10t)."),
        ]

        malware_commands = {
            "worm": [
                ("masscan --rate 10000 -p0-65535", "Scan massif (cd 10t)."),
                ("exploit/ms17-010", "Exploit EternalBlue, infecte 1-2 noeuds (cd 15t)."),
                ("./propagate --aggressive", "Force propagation (cd 12t)."),
                ("botnet deploy <miners|ddos>", "Deploie le botnet (cd 15/20t)."),
            ],
            "trojan": [
                ("msfvenom -p reverse_tcp", "Payload reverse shell (cd 10t)."),
                ("mimikatz sekurlsa::logonpasswords", "Dump credentials (cd 12t)."),
                ("ssh -D 1080 pivot@target", "Tunnel SOCKS (cd 10t)."),
                ("exfil --dns --encode base64", "Exfiltration DNS furtive (cd 12t)."),
            ],
            "ransomware": [
                ("encrypt --cipher aes-256-cbc", "Chiffre les fichiers (cd 12t)."),
                ("ransom --note DROP", "Depose une rancon (cd 10t)."),
                ("wmic shadowcopy delete", "Supprime les sauvegardes (cd 15t)."),
                ("tor-negotiate --btc-wallet", "Negocie paiement Tor (cd 20t)."),
            ],
            "rootkit": [
                ("insmod /dev/null/rootkit.ko", "Module noyau (cd 12t)."),
                ("syscall_hook --hide-pid", "Hook syscall (cd 15t)."),
                ("dd if=/dev/sda bs=512 count=1", "Infecte le bootloader (cd 15t)."),
                ("ld_preload inject /lib/libhook.so", "Injection LD_PRELOAD (cd 12t)."),
            ],
        }

        cmd_width = max(
            max(len(name) for name, _ in common_commands),
            max(len(name) for name, _ in malware_commands.get(mc, [])),
        )

        rows = [f"{name.ljust(cmd_width)} - {desc}" for name, desc in common_commands]
        rows.append("")
        rows.append(f"[{mc.upper()}]")
        rows.extend(
            f"{name.ljust(cmd_width)} - {desc}"
            for name, desc in malware_commands.get(mc, [])
        )

        title = "AVAILABLE COMMANDS"
        inner_width = max(len(title), *(len(row) for row in rows))
        boxed = []
        boxed.append("┌" + "─" * (inner_width + 2) + "┐")
        boxed.append(f"│ {title.ljust(inner_width)} │")
        boxed.append("├" + "─" * (inner_width + 2) + "┤")
        for row in rows:
            boxed.append(f"│ {row.ljust(inner_width)} │")
        boxed.append("└" + "─" * (inner_width + 2) + "┘")

        return {"ok": True, "output": "\n".join(boxed)}

    # Statut
    if cmd in ("status", "statut"):
        hack_str = "PRET" if state.special_cooldown == 0 else f"recharge ({state.special_cooldown} ticks)"
        msg = (
            f"Tick: {state.tick} | Malware: {state.malware_class} | "
            f"Noeuds infectes: {state.infected_count}/{state.total_nodes} | "
            f"CPU: {int(state.cpu_cycles)} | Mefiance: {round(state.suspicion, 1)}% | "
            f"Hack: {hack_str}"
        )
        return {"ok": True, "output": msg}

    # ── Commandes génériques ─────────────────────────────────────

    if cmd == "nmap" or cmd == "scan":
        flags = " ".join(args)
        if "-sS" in flags and "-T4" in flags and "-Pn" in flags:
            if _cd(state, "nmap_stealth") > 0:
                return {"ok": False, "output": f"[nmap furtif] Recharge — {_cd(state, 'nmap_stealth')} tick(s)."}
            bonus = 5
            state.cpu_cycles += bonus
            state.suspicion = max(0, state.suspicion - 1.5)
            _setcd(state, "nmap_stealth", 8)
            return {"ok": True, "output": f"Scan SYN furtif terminé. (+{bonus} CPU, méfiance -1.5%)"}
        if "-A" in flags and "-sV" in flags:
            if _cd(state, "nmap_aggr") > 0:
                return {"ok": False, "output": f"[nmap] Recharge — {_cd(state, 'nmap_aggr')} tick(s)."}
            bonus = 6
            state.cpu_cycles += bonus
            _setcd(state, "nmap_aggr", 6)
            return {"ok": True, "output": f"Scan agressif terminé. Surfaces d'attaque identifiées. (+{bonus} CPU)"}
        return {"ok": False, "output": 'Syntaxe: nmap -A -sV  ou  nmap -sS -T4 -Pn'}

    if cmd == "ifconfig":
        return {
            "ok": True,
            "output": (
                f"eth0: inet 10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}  "
                f"netmask 255.255.0.0\n"
                f"  Noeuds: {state.total_nodes} | Infectes: {state.infected_count} | "
                f"Interfaces compromises: {min(state.infected_count, 8)}"
            ),
        }

    if cmd == "whoami":
        names = {"worm": "w0rm_Agent", "trojan": "tr0jan_H0rse",
                 "ransomware": "ransom_L0ck", "rootkit": "r00t_gh0st"}
        return {
            "ok": True,
            "output": (
                f"uid=0(root) gid=0(root)\n"
                f"Identite: {names.get(state.malware_class, 'unknown')} [{state.malware_class.upper()}]\n"
                f"Tick: {state.tick} | Score: {state.score}"
            ),
        }

    if cmd == "ps" and args and args[0].lower() == "aux":
        if _cd(state, "ps_aux") > 0:
            return {"ok": False, "output": f"[ps aux] Recharge — {_cd(state, 'ps_aux')} tick(s)."}
        bonus = 2
        state.cpu_cycles += bonus
        procs = [
            "root       1  0.0  sshd: /usr/sbin/sshd",
            f"root     666  {round(state.suspicion/10,1)}  [malware/{state.malware_class}]",
            f"root     667  0.{random.randint(1,9)}  [c2_beacon]",
        ]
        if state.infected_count > 5:
            procs.append(f"root     668  1.2  [propagation_thread x{state.infected_count}]")
        _setcd(state, "ps_aux", 6)
        return {"ok": True, "output": "USER     PID  %CPU  COMMAND\n" + "\n".join(procs) + f"\n(+{bonus} CPU)"}

    if raw.lower().startswith("cat /etc/shadow"):
        if _cd(state, "shadow") > 0:
            return {"ok": False, "output": f"[shadow] Recharge — {_cd(state, 'shadow')} tick(s)."}
        bonus = 8
        state.cpu_cycles += bonus
        state.suspicion = min(100, state.suspicion + 1.0)
        hashes = [
            "root:$6$rNd0m$K8x9zLqV3mH7wP2jF5nG1bYcT4vA6dR0eI8uQ3sW7kJ:19458:0:99999:7:::",
            "admin:$6$S4lt3d$Fp2xR7mN1qL9wK3jH6gT8bYcU5vA0dE2oI4uQ7sW3kJ:19458:0:99999:7:::",
        ]
        _setcd(state, "shadow", 12)
        return {"ok": True, "output": "\n".join(hashes) + f"\nHash extraits. (+{bonus} CPU, méfiance +1%)"}

    if cmd == "tcpdump":
        flags = " ".join(args)
        if "-i" in flags and "-nn" in flags:
            if _cd(state, "tcpdump") > 0:
                return {"ok": False, "output": f"[tcpdump] Recharge — {_cd(state, 'tcpdump')} tick(s)."}
            bonus = 7
            state.cpu_cycles += bonus
            _setcd(state, "tcpdump", 10)
            return {
                "ok": True,
                "output": (
                    f"tcpdump: listening on eth0\n"
                    f"  {state.infected_count * 47} packets captured\n"
                    f"  {state.infected_count * 3} packets with credentials detected\n"
                    f"(+{bonus} CPU)"
                ),
            }
        return {"ok": False, "output": 'Syntaxe: tcpdump -i eth0 -nn'}

    if cmd == "phishing":
        if args and args[0].lower() == "start":
            if _cd(state, "phishing") > 0:
                return {"ok": False, "output": f"[phishing] Recharge — {_cd(state, 'phishing')} tick(s)."}
            # Gain plafonné : ne scale plus linéairement avec les noeuds infectés
            gain = max(4, int(state.infected_count * 0.5))
            state.cpu_cycles += gain
            _setcd(state, "phishing", 10)
            return {"ok": True, "output": f"Campagne lancée. Plusieurs utilisateurs ont cliqué. (+{gain} CPU)"}
        return {"ok": False, "output": 'Syntaxe: phishing start'}

    # ── Commandes WORM ───────────────────────────────────────────
    if state.malware_class == "worm":
        if cmd == "masscan":
            flags = " ".join(args)
            if "--rate" in flags and "-p0-65535" in flags:
                if _cd(state, "masscan") > 0:
                    return {"ok": False, "output": f"[masscan] Recharge — {_cd(state, 'masscan')} tick(s)."}
                bonus = 12
                state.cpu_cycles += bonus
                state.suspicion = min(100, state.suspicion + 2.0)
                _setcd(state, "masscan", 10)
                return {
                    "ok": True,
                    "output": (
                        f"Masscan: {state.total_nodes * 65535} ports scannés\n"
                        f"  {random.randint(12, 30)} services vulnérables. (+{bonus} CPU, méfiance +2%)"
                    ),
                }
            return {"ok": False, "output": 'Syntaxe: masscan --rate 10000 -p0-65535'}

        if raw.lower().startswith("exploit/ms17-010"):
            if _cd(state, "ms17") > 0:
                return {"ok": False, "output": f"[exploit] Recharge — {_cd(state, 'ms17')} tick(s)."}
            bonus = 10
            state.cpu_cycles += bonus
            state.suspicion = min(100, state.suspicion + 3.0)
            candidates = [n for n in state.nodes if not n.infected and not n.quarantined]
            infected_extra = 0
            if candidates:
                to_infect = random.sample(candidates, min(2, len(candidates)))
                for n in to_infect:
                    n.infected = True
                    infected_extra += 1
            _setcd(state, "ms17", 15)
            return {
                "ok": True,
                "output": (
                    f"[*] EternalBlue lancé — {infected_extra} nœud(s) infecté(s). "
                    f"(+{bonus} CPU, méfiance +3%)"
                ),
            }

        if raw.lower().startswith("./propagate") and "--aggressive" in raw.lower():
            if _cd(state, "propagate") > 0:
                return {"ok": False, "output": f"[propagate] Recharge — {_cd(state, 'propagate')} tick(s)."}
            bonus = 10
            state.cpu_cycles += bonus
            state.suspicion = min(100, state.suspicion + 2.0)
            _setcd(state, "propagate", 12)
            return {"ok": True, "output": f"Propagation agressive sur {state.infected_count} hôtes. (+{bonus} CPU, méfiance +2%)"}

        if cmd == "botnet" and args and args[0].lower() == "deploy":
            if len(args) >= 2:
                subtype = args[1].lower()
                if subtype == "miners":
                    if _cd(state, "botnet_miners") > 0:
                        return {"ok": False, "output": f"[botnet miners] Recharge — {_cd(state, 'botnet_miners')} tick(s)."}
                    bonus = 15
                    state.cpu_cycles += bonus
                    state.suspicion = min(100, state.suspicion + 2.0)
                    _setcd(state, "botnet_miners", 15)
                    return {"ok": True, "output": f"Mining déployé. Hashrate: {state.infected_count * 12.5} MH/s (+{bonus} CPU, méfiance +2%)"}
                elif subtype == "ddos":
                    if _cd(state, "botnet_ddos") > 0:
                        return {"ok": False, "output": f"[botnet ddos] Recharge — {_cd(state, 'botnet_ddos')} tick(s)."}
                    bonus = 18
                    state.cpu_cycles += bonus
                    state.suspicion = min(100, state.suspicion + 5.0)
                    _setcd(state, "botnet_ddos", 20)
                    return {"ok": True, "output": f"DDoS depuis {state.infected_count} bots. (+{bonus} CPU, méfiance +5%)"}
            return {"ok": False, "output": 'Syntaxe: botnet deploy <miners|ddos>'}

    # ── Commandes TROJAN ─────────────────────────────────────────
    if state.malware_class == "trojan":
        if cmd == "msfvenom":
            flags = " ".join(args)
            if "-p" in flags and "reverse_tcp" in flags:
                if _cd(state, "msfvenom") > 0:
                    return {"ok": False, "output": f"[msfvenom] Recharge — {_cd(state, 'msfvenom')} tick(s)."}
                bonus = 10
                state.cpu_cycles += bonus
                _setcd(state, "msfvenom", 10)
                return {
                    "ok": True,
                    "output": (
                        f"Payload: windows/meterpreter/reverse_tcp\n"
                        f"  LHOST=10.0.0.{random.randint(1,254)} LPORT=4444 | "
                        f"{random.randint(350,500)} bytes. (+{bonus} CPU)"
                    ),
                }
            return {"ok": False, "output": 'Syntaxe: msfvenom -p reverse_tcp'}

        if cmd == "mimikatz" and args and "sekurlsa::logonpasswords" in args[0].lower():
            if _cd(state, "mimikatz") > 0:
                return {"ok": False, "output": f"[mimikatz] Recharge — {_cd(state, 'mimikatz')} tick(s)."}
            bonus = 12
            state.cpu_cycles += bonus
            _setcd(state, "mimikatz", 12)
            return {
                "ok": True,
                "output": (
                    f"mimikatz # sekurlsa::logonpasswords\n"
                    f"  NTLM: {'{:032x}'.format(random.getrandbits(128))}\n"
                    f"  {random.randint(3, 8)} credentials extraits. (+{bonus} CPU)"
                ),
            }

        if cmd == "ssh" and "-D" in " ".join(args):
            if "1080" in " ".join(args):
                if _cd(state, "ssh_tunnel") > 0:
                    return {"ok": False, "output": f"[ssh] Recharge — {_cd(state, 'ssh_tunnel')} tick(s)."}
                bonus = 10
                state.cpu_cycles += bonus
                _setcd(state, "ssh_tunnel", 10)
                return {"ok": True, "output": f"Tunnel SOCKS5 127.0.0.1:1080 ouvert via {state.infected_count} noeuds. (+{bonus} CPU)"}
            return {"ok": False, "output": 'Syntaxe: ssh -D 1080 pivot@target'}

        if cmd == "exfil":
            flags = " ".join(args)
            if "--dns" in flags and "--encode" in flags and "base64" in flags:
                if _cd(state, "exfil") > 0:
                    return {"ok": False, "output": f"[exfil] Recharge — {_cd(state, 'exfil')} tick(s)."}
                bonus = 15
                state.cpu_cycles += bonus
                state.suspicion = max(0, state.suspicion - 1.5)
                _setcd(state, "exfil", 12)
                return {
                    "ok": True,
                    "output": (
                        f"Exfiltration DNS — {random.randint(50, 200)} Ko via dns.tunnel.corp.\n"
                        f"Aucune alerte IDS. (+{bonus} CPU, méfiance -1.5%)"
                    ),
                }
            return {"ok": False, "output": 'Syntaxe: exfil --dns --encode base64'}

    # ── Commandes RANSOMWARE ─────────────────────────────────────
    if state.malware_class == "ransomware":
        if cmd == "encrypt":
            flags = " ".join(args)
            if "--cipher" in flags and "aes-256-cbc" in flags:
                if _cd(state, "encrypt") > 0:
                    return {"ok": False, "output": f"[encrypt] Recharge — {_cd(state, 'encrypt')} tick(s)."}
                bonus = 12
                state.cpu_cycles += bonus
                state.suspicion = min(100, state.suspicion + 3.0)
                _setcd(state, "encrypt", 12)
                return {
                    "ok": True,
                    "output": (
                        f"AES-256-CBC sur {state.infected_count} machines.\n"
                        f"  {state.infected_count * random.randint(800, 2000)} fichiers chiffrés. "
                        f"(+{bonus} CPU, méfiance +3%)"
                    ),
                }
            return {"ok": False, "output": 'Syntaxe: encrypt --cipher aes-256-cbc'}

        if cmd == "ransom":
            flags = " ".join(args)
            if "--note" in flags and "DROP" in raw:
                if _cd(state, "ransom_note") > 0:
                    return {"ok": False, "output": f"[ransom] Recharge — {_cd(state, 'ransom_note')} tick(s)."}
                bonus = 10
                state.cpu_cycles += bonus
                state.suspicion = min(100, state.suspicion + 2.0)
                _setcd(state, "ransom_note", 10)
                return {
                    "ok": True,
                    "output": (
                        f"Note déposée sur {state.infected_count} machines.\n"
                        f"  \"Payez 2.5 BTC.\" — READ_ME.txt créé. (+{bonus} CPU, méfiance +2%)"
                    ),
                }
            return {"ok": False, "output": 'Syntaxe: ransom --note DROP'}

        if cmd == "wmic" and args and "shadowcopy" in " ".join(args).lower() and "delete" in " ".join(args).lower():
            if _cd(state, "wmic") > 0:
                return {"ok": False, "output": f"[wmic] Recharge — {_cd(state, 'wmic')} tick(s)."}
            bonus = 11
            state.cpu_cycles += bonus
            state.suspicion = min(100, state.suspicion + 3.5)
            _setcd(state, "wmic", 15)
            return {
                "ok": True,
                "output": (
                    f"{random.randint(5, 15)} points de restauration détruits.\n"
                    f"Récupération impossible sans clé. (+{bonus} CPU, méfiance +3.5%)"
                ),
            }

        if raw.lower().startswith("tor-negotiate") and "--btc-wallet" in raw.lower():
            if _cd(state, "tor_negotiate") > 0:
                return {"ok": False, "output": f"[tor] Recharge — {_cd(state, 'tor_negotiate')} tick(s)."}
            bonus = 18
            state.cpu_cycles += bonus
            state.suspicion = min(100, state.suspicion + 1.0)
            _setcd(state, "tor_negotiate", 20)
            return {
                "ok": True,
                "output": (
                    f"Connexion Tor — wallet bc1q{'{:040x}'.format(random.getrandbits(160))[:40]}\n"
                    f"Paiement partiel reçu. (+{bonus} CPU, méfiance +1%)"
                ),
            }

    # ── Commandes ROOTKIT ────────────────────────────────────────
    if state.malware_class == "rootkit":
        if cmd == "insmod" and "/dev/null/rootkit.ko" in raw:
            if _cd(state, "insmod") > 0:
                return {"ok": False, "output": f"[insmod] Recharge — {_cd(state, 'insmod')} tick(s)."}
            bonus = 10
            state.cpu_cycles += bonus
            state.suspicion = max(0, state.suspicion - 2.0)
            _setcd(state, "insmod", 12)
            return {
                "ok": True,
                "output": (
                    f"rootkit.ko injecté. Hooks: sys_read, sys_write, sys_getdents64.\n"
                    f"Processus masqués kernel. (+{bonus} CPU, méfiance -2%)"
                ),
            }

        if cmd == "syscall_hook" and "--hide-pid" in raw.lower():
            if _cd(state, "syscall_hook") > 0:
                return {"ok": False, "output": f"[syscall] Recharge — {_cd(state, 'syscall_hook')} tick(s)."}
            bonus = 12
            state.cpu_cycles += bonus
            state.suspicion = max(0, state.suspicion - 3.0)
            _setcd(state, "syscall_hook", 15)
            return {"ok": True, "output": f"PID masqué dans /proc. Invisible pour ps/top/htop. (+{bonus} CPU, méfiance -3%)"}

        if cmd == "dd" and "/dev/sda" in raw:
            flags = " ".join(args)
            if "bs=512" in flags and "count=1" in flags:
                if _cd(state, "dd_mbr") > 0:
                    return {"ok": False, "output": f"[dd] Recharge — {_cd(state, 'dd_mbr')} tick(s)."}
                bonus = 11
                state.cpu_cycles += bonus
                state.suspicion = min(100, state.suspicion + 1.0)
                _setcd(state, "dd_mbr", 15)
                return {"ok": True, "output": f"MBR infecté. 512 bytes copiés. Persistance totale. (+{bonus} CPU, méfiance +1%)"}
            return {"ok": False, "output": 'Syntaxe: dd if=/dev/sda bs=512 count=1'}

        if cmd == "ld_preload" and "inject" in raw.lower() and "/lib/libhook.so" in raw:
            if _cd(state, "ld_preload") > 0:
                return {"ok": False, "output": f"[ld_preload] Recharge — {_cd(state, 'ld_preload')} tick(s)."}
            bonus = 15
            state.cpu_cycles += bonus
            state.suspicion = max(0, state.suspicion - 2.5)
            _setcd(state, "ld_preload", 12)
            return {"ok": True, "output": f"LD_PRELOAD:/lib/libhook.so injecté. Toutes les fonctions libc interceptées. (+{bonus} CPU, méfiance -2.5%)"}

    # ── Hack spécial de classe ────────────────────────────────────
    if cmd in ("hack", "special", "ability"):
        if state.special_cooldown > 0:
            return {
                "ok": False,
                "output": f"Hack en recharge... ({state.special_cooldown} ticks restants)",
            }

        if state.malware_class == "worm":
            candidates = [n for n in state.nodes if not n.infected and not n.quarantined and not n.honeypot]
            targets = random.sample(candidates, min(4, len(candidates)))
            for n in targets:
                n.infected = True
            state.special_cooldown = 15
            state.suspicion = min(100.0, state.suspicion + 5.0)
            return {"ok": True, "output": f"[WORM] Propagation de masse — {len(targets)} nœud(s) infecté(s). (méfiance +5%, cd 15t)"}

        elif state.malware_class == "trojan":
            reduction = round(min(state.suspicion, 25.0), 1)
            state.suspicion = max(0.0, state.suspicion - reduction)
            state.special_cooldown = 20
            return {"ok": True, "output": f"[TROJAN] Mode fantôme — méfiance -{reduction}%. (cd 20t)"}

        elif state.malware_class == "ransomware":
            # Réduit de 200 à 100 CPU pour aligner avec la nouvelle économie
            bonus = 100
            state.cpu_cycles += bonus
            state.suspicion = min(100.0, state.suspicion + 8.0)
            state.special_cooldown = 25
            return {"ok": True, "output": f"[RANSOMWARE] Paiement forcé — +{bonus} CPU. (méfiance +8%, cd 25t)"}

        elif state.malware_class == "rootkit":
            old_sus = round(state.suspicion, 1)
            state.suspicion = 0.0
            state.special_cooldown = 30
            return {"ok": True, "output": f"[ROOTKIT] Zero-trace — méfiance {old_sus}% → 0%. (cd 30t)"}

        return {"ok": False, "output": "Classe de malware inconnue."}

    # Upgrade via terminal
    if cmd == "upgrade":
        if not args:
            return {"ok": False, "output": 'Syntaxe: upgrade <nom_amélioration>'}
        target = " ".join(args).lower()
        upgrades = get_all_upgrades()
        found = None
        for u in upgrades:
            allowed = u["effect_json"].get("allowed_malware", [])
            if allowed and state.malware_class not in allowed:
                continue
            if target in u["name"].lower():
                found = u
                break
        if not found:
            return {"ok": False, "output": f"Aucune amélioration '{target}' pour {state.malware_class}."}
        result = buy_upgrade(state, found["id"])
        if result.get("ok"):
            return {"ok": True, "output": f"'{found['name']}' installée. CPU restants: {result['remaining_cycles']}."}
        return {"ok": False, "output": result.get("error", "Achat impossible.")}

    if cmd == "log" and args and args[0].lower() == "suspicion":
        return {"ok": True, "output": f"Méfiance: {round(state.suspicion, 1)}%. Patch: {bool(state.patch_deployed)}."}

    return {"ok": False, "output": f"Commande inconnue: {cmd}. Tapez 'help'."}


def buy_upgrade(state: GameState, upgrade_id: int) -> dict:
    """Achète une amélioration si le joueur a les ressources."""
    if upgrade_id in state.purchased_upgrades:
        return {"ok": False, "error": "Amélioration déjà achetée."}

    upgrades = get_all_upgrades()
    upgrade = next((u for u in upgrades if u["id"] == upgrade_id), None)
    if not upgrade:
        return {"ok": False, "error": "Amélioration inconnue."}

    allowed = upgrade["effect_json"].get("allowed_malware")
    if allowed and state.malware_class not in allowed:
        return {"ok": False, "error": "Cette amélioration n'est pas compatible avec votre malware."}

    if state.cpu_cycles < upgrade["cost"]:
        return {"ok": False, "error": f"Pas assez de CPU Cycles ({upgrade['cost']} requis)."}

    if upgrade["tier"] > 1:
        same_branch = [u for u in upgrades
                       if u["branch"] == upgrade["branch"]
                       and u["tier"] == upgrade["tier"] - 1
                       and (not u["effect_json"].get("allowed_malware")
                            or state.malware_class in u["effect_json"]["allowed_malware"])]
        if same_branch and not any(u["id"] in state.purchased_upgrades for u in same_branch):
            return {"ok": False, "error": "Vous devez d'abord acheter l'amélioration précédente."}

    state.cpu_cycles -= upgrade["cost"]
    state.purchased_upgrades.append(upgrade_id)

    effect = upgrade["effect_json"]
    if "propagation_bonus" in effect:
        state.propagation_mod += effect["propagation_bonus"]
    if "stealth" in effect:
        state.stealth_mod += effect["stealth"]
    if "income_bonus" in effect:
        state.income_mod += effect["income_bonus"]
    if "passive_income" in effect:
        state.passive_income_bonus += effect["passive_income"]

    state.stealth_mod += upgrade["stealth_mod"]

    return {"ok": True, "upgrade": upgrade["name"], "remaining_cycles": round(state.cpu_cycles, 1)}
