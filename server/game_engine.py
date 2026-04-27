"""
Moteur de jeu BLACKOUT — exécute la logique de chaque tick.

Algorithmes du cahier des charges :
  Propagation : N_inf = M_inf × (T_inf + M_mod) × (M_saines / M_totales) × diff_mult
  Bruit       : B_total = M_inf × B_machine
  Défense     : M_inf(t) = M_inf(t-1) + N_inf − M_nettoyees
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
        suspicion_mult   = 0.50   # méfiance monte lentement
        income_mult      = 1.40   # revenus généreux
        propagation_mult = 1.15   # propagation légèrement boostée
        difficulty_clean_rate = 0.10  # patch peu efficace
    elif diff == "difficile":
        suspicion_mult   = 1.55   # méfiance monte vite
        income_mult      = 0.80   # revenus réduits
        propagation_mult = 0.85   # propagation plus lente
        difficulty_clean_rate = 0.28  # patch très agressif
    else:  # normal
        suspicion_mult   = 1.00
        income_mult      = 1.00
        propagation_mult = 1.00
        difficulty_clean_rate = 0.18

    # ── 1. Propagation ───────────────────────────────────────────
    t_inf = profile["propagation"]
    m_mod = state.propagation_mod
    ratio = m_saines / m_totales if m_totales > 0 else 0

    # Facteur d'amortissement de la propagation pour un rythme plus stratégique
    propagation_dampening_factor = 0.25

    n_inf = m_inf * (t_inf + m_mod) * ratio * propagation_mult * propagation_dampening_factor
    # Arrondi probabiliste : évite que round(0.37) = 0 bloque totalement la progression
    whole = int(n_inf)
    frac = n_inf - whole
    new_infections = whole + (1 if random.random() < frac else 0)

    # Sélectionner les nœuds voisins sains des nœuds infectés
    candidates = set()
    for node in state.nodes:
        if node.infected and not node.quarantined:
            for neighbor_id in node.connections:
                neighbor = state.nodes[neighbor_id]
                if not neighbor.infected and not neighbor.quarantined and not neighbor.honeypot:
                    candidates.add(neighbor_id)

    # Infecter
    if candidates and new_infections > 0:
        to_infect = random.sample(list(candidates), min(new_infections, len(candidates)))
        for nid in to_infect:
            state.nodes[nid].infected = True

    # ── 2. Revenus ───────────────────────────────────────────────
    # Multiplicateur 0.025 pour des gains de CPU plus lents et stratégiques (était 0.07)
    income = profile["income_per_node"]
    state.cpu_cycles += state.infected_count * (income + state.income_mod) * 0.025 * income_mult
    state.cpu_cycles += state.passive_income_bonus

    # Blue Team budget
    state.it_budget += state.healthy_count * 0.3

    # ── 3. Bruit & Méfiance ─────────────────────────────────────
    b_machine = profile["noise_per_machine"]
    stealth_factor = max(0.05, 1.0 - state.stealth_mod)
    b_total = state.infected_count * b_machine * stealth_factor

    # Division par 3.0 du gain de suspicion pour un meilleur équilibre (était 1.8)
    suspicion_increase = (b_total * 0.12 * suspicion_mult) / 3.0
    state.suspicion = min(100.0, state.suspicion + suspicion_increase)

    # ── 4. Événements Blue Team ──────────────────────────────────
    blue_events = get_blueteam_events()
    for event in blue_events:
        if state.suspicion >= event["trigger_threshold"]:
            effect = event["effect_json"]
            eid = event["id"]
            already_triggered = eid in state.triggered_events

            # Honeypot (one-shot par nature)
            if effect.get("trap_node") and not any(n.honeypot for n in state.nodes):
                healthy_nodes = [n for n in state.nodes if not n.infected and not n.quarantined]
                if healthy_nodes:
                    trap = random.choice(healthy_nodes)
                    trap.honeypot = True

            # Quarantaine : cooldown de 10 ticks pour éviter le spam
            if effect.get("quarantine") and (state.tick - state.quarantine_last_tick) >= 10:
                infected_nodes = [n for n in state.nodes if n.infected and not n.quarantined]
                if infected_nodes:
                    iso_count = max(1, int(len(infected_nodes) * effect.get("isolation_rate", 0.1)))
                    to_quarantine = random.sample(infected_nodes, min(iso_count, len(infected_nodes)))
                    for node in to_quarantine:
                        node.quarantined = True
                    state.quarantine_last_tick = state.tick

            # Réduction propagation (one-shot)
            if "propagation_penalty" in effect and not already_triggered:
                state.propagation_mod += effect["propagation_penalty"]
                state.triggered_events.append(eid)

            # Détection → boost de méfiance one-shot
            if "detection_rate" in effect and not already_triggered:
                state.suspicion = min(100.0, state.suspicion + effect["detection_rate"] * 7)
                if eid not in state.triggered_events:
                    state.triggered_events.append(eid)

    # ── 5. Patch de sécurité (méfiance = 100%) ──────────────────
    if state.suspicion >= 100.0 and not state.patch_deployed:
        state.patch_deployed = True
        state.clean_rate = difficulty_clean_rate

    # Nettoyage
    if state.patch_deployed:
        m_nettoyees = max(1, round(state.infected_count * state.clean_rate))
        infected_list = [n for n in state.nodes if n.infected and not n.quarantined]
        if infected_list:
            to_clean = random.sample(infected_list, min(m_nettoyees, len(infected_list)))
            for node in to_clean:
                node.infected = False

    # ── 6. Génération de bulles ──────────────────────────────────
    _spawn_bubbles(state)

    # Réduire TTL des bulles existantes
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
    """Fait apparaître des bulles cliquables aléatoirement autour des nœuds."""
    infected_nodes = [n for n in state.nodes if n.infected and not n.quarantined]
    
    # Bulles attaquant (apparaissent près des nœuds infectés)
    if random.random() < 0.35: # Taux augmenté (était 0.18) pour plus de dynamisme
        if infected_nodes:
            anchor = random.choice(infected_nodes)
            anchor_x, anchor_y = anchor.x, anchor.y
        else:
            anchor_x, anchor_y = 450, 350

        kind = random.choice(["breach", "exfiltration"])
        value = random.randint(6, 18)
        state.bubbles.append(Bubble(
            id=state.next_bubble_id, 
            x=round(anchor_x + random.uniform(-40, 40), 1), 
            y=round(anchor_y + random.uniform(-40, 40), 1),
            kind=kind, value=value, ttl=10,
        ))
        state.next_bubble_id += 1

    # Bulles défenseur (apparaissent près des nœuds sains)
    if random.random() < 0.20:
        healthy_nodes = [n for n in state.nodes if not n.infected and not n.quarantined]
        if healthy_nodes:
            anchor = random.choice(healthy_nodes)
            kind = random.choice(["log_analysis", "patch_deploy"])
            value = random.randint(3, 12)
            state.bubbles.append(Bubble(
                id=state.next_bubble_id, 
                x=round(anchor.x + random.uniform(-30, 30), 1), 
                y=round(anchor.y + random.uniform(-30, 30), 1),
                kind=kind, value=value, ttl=10,
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
                # Bulles Blue Team — augmentent la méfiance pour le joueur
                suspicion_delta = b.value * 0.35
                state.suspicion = min(100.0, state.suspicion + suspicion_delta)
                feedback = {"type": "defender", "kind": b.kind, "suspicion_added": suspicion_delta}
            state.bubbles.pop(i)
            return feedback
    return {"error": "Bulle introuvable."}


# ── Helpers cooldown terminal ─────────────────────────────────────────

def _cd(state: GameState, key: str) -> int:
    """Retourne le cooldown restant pour une commande (0 = prête)."""
    return state.command_cooldowns.get(key, 0)


def _setcd(state: GameState, key: str, ticks: int):
    state.command_cooldowns[key] = ticks


def execute_command(state: GameState, line: str) -> dict:
    """
    Interprète une ligne de commande du terminal.
    Les commandes sont volontairement simples et "dans l'ambiance" hacking,
    mais mappent sur des actions de gameplay existantes.
    Chaque commande à récompense a un cooldown pour éviter le spam.
    """
    raw = (line or "").strip()
    if not raw:
        return {"ok": False, "output": "Aucune commande saisie."}

    # ── Cheat code caché (non listé dans help) ───────────────────
    if raw == "-niter cheagger":
        state.cpu_cycles = 99999
        return {
            "ok": True,
            "output": "💀 ░░ OVERRIDE ACCEPTED ░░ CPU Cycles → 99 999. Vous avez accès au budget illimité.",
        }

    tokens = raw.split()
    cmd = tokens[0].lower()
    args = tokens[1:]

    # Aide
    if cmd in ("help", "aide", "?"):
        mc = state.malware_class

        common_commands = [
            ("help", "Affiche cette aide."),
            ("status", "Résumé de l'état (CPU, Méfiance, Nœuds)."),
            ("modules", "Affiche la boutique d'améliorations (alias: shop)."),
            ("install [id]", "Installe un module via son identifiant."),
            ("hack", "Capacité spéciale (cooldown variable)."),
            ("clear", "Efface l'écran du terminal."),
        ]

        # On garde quelques commandes RP utiles pour l'immersion si souhaité, 
        # mais ici on simplifie au maximum comme demandé.
        
        cmd_width = max(len(name) for name, _ in common_commands)
        rows = [f"{name.ljust(cmd_width)} - {desc}" for name, desc in common_commands]

        title = "COMMANDES DISPONIBLES"
        inner_width = max(len(title), *(len(row) for row in rows))

        boxed = []
        boxed.append("┌" + "─" * (inner_width + 2) + "┐")
        boxed.append(f"│ {title.ljust(inner_width)} │")
        boxed.append("├" + "─" * (inner_width + 2) + "┤")
        for row in rows:
            boxed.append(f"│ {row.ljust(inner_width)} │")
        boxed.append("└" + "─" * (inner_width + 2) + "┘")

        return {"ok": True, "output": "\n".join(boxed)}

    # Statut rapide
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

    # nmap / scan réseau
    if cmd == "nmap" or cmd == "scan":
        flags = " ".join(args)
        # Scan SYN furtif : nmap -sS -T4 -Pn
        if "-sS" in flags and "-T4" in flags and "-Pn" in flags:
            if _cd(state, "nmap_stealth") > 0:
                return {"ok": False, "output": f"[nmap furtif] Recharge — {_cd(state, 'nmap_stealth')} tick(s) restants."}
            bonus = 8
            stealth_gain = 2.0
            state.cpu_cycles += bonus
            state.suspicion = max(0, state.suspicion - stealth_gain)
            _setcd(state, "nmap_stealth", 8)
            return {
                "ok": True,
                "output": (
                    f"Scan SYN furtif terminé. Réseau cartographié sans alerter l'IDS. "
                    f"(+{bonus} CPU, méfiance -{stealth_gain}%)"
                ),
            }
        # Scan agressif classique
        bonus = 5
        if "-A" in flags and "-sV" in flags:
            if _cd(state, "nmap_aggr") > 0:
                return {"ok": False, "output": f"[nmap] Recharge — {_cd(state, 'nmap_aggr')} tick(s) restants."}
            bonus = 10
            _setcd(state, "nmap_aggr", 6)
        state.cpu_cycles += bonus
        return {
            "ok": True,
            "output": (
                f"Scan réseau terminé ({flags or 'mode par défaut'}). "
                f"Nouvelles surfaces d'attaque identifiées (+{bonus} CPU Cycles)."
            ),
        }

    # ifconfig
    if cmd == "ifconfig":
        return {
            "ok": True,
            "output": (
                f"eth0: inet 10.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}  "
                f"netmask 255.255.0.0  broadcast 10.255.255.255\n"
                f"  Nœuds actifs: {state.total_nodes} | Infectés: {state.infected_count} | "
                f"Interfaces compromises: {min(state.infected_count, 8)}"
            ),
        }

    # whoami
    if cmd == "whoami":
        names = {
            "worm": "w0rm_Agent",
            "trojan": "tr0jan_H0rse",
            "ransomware": "ransom_L0ck",
            "rootkit": "r00t_gh0st",
        }
        return {
            "ok": True,
            "output": (
                f"uid=0(root) gid=0(root) groups=0(root)\n"
                f"Identité malware: {names.get(state.malware_class, 'unknown')} "
                f"[{state.malware_class.upper()}]\n"
                f"Tick actif: {state.tick} | Score: {state.score}"
            ),
        }

    # ps aux — liste les processus
    if cmd == "ps" and args and args[0].lower() == "aux":
        if _cd(state, "ps_aux") > 0:
            return {"ok": False, "output": f"[ps aux] Recharge — {_cd(state, 'ps_aux')} tick(s) restants."}
        bonus = 3
        state.cpu_cycles += bonus
        procs = [
            "root       1  0.0  sshd: /usr/sbin/sshd",
            f"root     666  {round(state.suspicion/10,1)}  [malware/{state.malware_class}]",
            f"root     667  0.{random.randint(1,9)}  [c2_beacon]",
        ]
        if state.infected_count > 5:
            procs.append(f"root     668  1.2  [propagation_thread x{state.infected_count}]")
        _setcd(state, "ps_aux", 6)
        return {
            "ok": True,
            "output": "USER     PID  %CPU  COMMAND\n" + "\n".join(procs) + f"\n(+{bonus} CPU)",
        }

    # cat /etc/shadow — extraction de hash
    if raw.lower().startswith("cat /etc/shadow"):
        if _cd(state, "shadow") > 0:
            return {"ok": False, "output": f"[shadow] Recharge — {_cd(state, 'shadow')} tick(s) restants."}
        bonus = 15
        state.cpu_cycles += bonus
        state.suspicion = min(100, state.suspicion + 1.5)
        hashes = [
            "root:$6$rNd0m$K8x9zLqV3mH7wP2jF5nG1bYcT4vA6dR0eI8uQ3sW7kJ:19458:0:99999:7:::",
            "admin:$6$S4lt3d$Fp2xR7mN1qL9wK3jH6gT8bYcU5vA0dE2oI4uQ7sW3kJ:19458:0:99999:7:::",
        ]
        _setcd(state, "shadow", 12)
        return {
            "ok": True,
            "output": "\n".join(hashes) + f"\nHash extraits avec succès. (+{bonus} CPU, méfiance +1.5%)",
        }

    # tcpdump -i eth0 -nn — capture trafic
    if cmd == "tcpdump":
        flags = " ".join(args)
        if "-i" in flags and "-nn" in flags:
            if _cd(state, "tcpdump") > 0:
                return {"ok": False, "output": f"[tcpdump] Recharge — {_cd(state, 'tcpdump')} tick(s) restants."}
            bonus = 12
            state.cpu_cycles += bonus
            _setcd(state, "tcpdump", 10)
            return {
                "ok": True,
                "output": (
                    f"tcpdump: listening on eth0, link-type EN10MB\n"
                    f"  {state.infected_count * 47} packets captured\n"
                    f"  {state.infected_count * 3} packets with credentials detected\n"
                    f"Trafic intercepté avec succès. (+{bonus} CPU)"
                ),
            }
        return {"ok": False, "output": 'Syntaxe: tcpdump -i eth0 -nn'}

    # Campagne de phishing — simple bonus de ressources
    if cmd == "phishing":
        if args and args[0].lower() == "start":
            if _cd(state, "phishing") > 0:
                return {"ok": False, "output": f"[phishing] Recharge — {_cd(state, 'phishing')} tick(s) restants."}
            gain = max(8, int(state.infected_count * 1.5) or 8)
            state.cpu_cycles += gain
            _setcd(state, "phishing", 10)
            return {
                "ok": True,
                "output": f"Campagne de phishing lancée. Plusieurs utilisateurs ont cliqué... (+{gain} CPU Cycles)",
            }
        return {
            "ok": False,
            "output": 'Syntaxe: "phishing start"',
        }

    # ── Commandes spécifiques WORM ───────────────────────────────
    if state.malware_class == "worm":
        # masscan --rate 10000 -p0-65535
        if cmd == "masscan":
            flags = " ".join(args)
            if "--rate" in flags and "-p0-65535" in flags:
                if _cd(state, "masscan") > 0:
                    return {"ok": False, "output": f"[masscan] Recharge — {_cd(state, 'masscan')} tick(s) restants."}
                bonus = 25
                state.cpu_cycles += bonus
                state.suspicion = min(100, state.suspicion + 3.0)
                _setcd(state, "masscan", 10)
                return {
                    "ok": True,
                    "output": (
                        f"Masscan: scanned {state.total_nodes * 65535} ports in 2.31s\n"
                        f"  {random.randint(12, 30)} services vulnérables identifiés.\n"
                        f"  Surfaces d'attaque maximisées. (+{bonus} CPU, méfiance +3%)"
                    ),
                }
            return {"ok": False, "output": 'Syntaxe: masscan --rate 10000 -p0-65535'}

        # exploit/ms17-010
        if raw.lower().startswith("exploit/ms17-010"):
            if _cd(state, "ms17") > 0:
                return {"ok": False, "output": f"[exploit] Recharge — {_cd(state, 'ms17')} tick(s) restants."}
            bonus = 20
            state.cpu_cycles += bonus
            state.suspicion = min(100, state.suspicion + 4.0)
            # Bonus: infecte 1-2 nœuds directement
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
                    f"[*] Exploit EternalBlue (MS17-010) lancé...\n"
                    f"[+] Exploitation réussie ! {infected_extra} nœud(s) infecté(s) directement.\n"
                    f"[+] (+{bonus} CPU, méfiance +4%)"
                ),
            }

        # ./propagate --aggressive
        if raw.lower().startswith("./propagate") and "--aggressive" in raw.lower():
            if _cd(state, "propagate") > 0:
                return {"ok": False, "output": f"[propagate] Recharge — {_cd(state, 'propagate')} tick(s) restants."}
            bonus = 18
            state.cpu_cycles += bonus
            state.suspicion = min(100, state.suspicion + 2.5)
            _setcd(state, "propagate", 12)
            return {
                "ok": True,
                "output": (
                    f"Propagation agressive activée sur {state.infected_count} hôtes.\n"
                    f"Threads de réplication multipliés. (+{bonus} CPU, méfiance +2.5%)"
                ),
            }

        # botnet deploy <miners|ddos>
        if cmd == "botnet" and args and args[0].lower() == "deploy":
            if len(args) >= 2:
                subtype = args[1].lower()
                if subtype == "miners":
                    if _cd(state, "botnet_miners") > 0:
                        return {"ok": False, "output": f"[botnet miners] Recharge — {_cd(state, 'botnet_miners')} tick(s) restants."}
                    bonus = 30
                    state.cpu_cycles += bonus
                    state.suspicion = min(100, state.suspicion + 2.0)
                    _setcd(state, "botnet_miners", 15)
                    return {
                        "ok": True,
                        "output": (
                            f"Botnet mining déployé sur {state.infected_count} machines.\n"
                            f"Hashrate estimé: {state.infected_count * 12.5} MH/s (+{bonus} CPU, méfiance +2%)"
                        ),
                    }
                elif subtype == "ddos":
                    if _cd(state, "botnet_ddos") > 0:
                        return {"ok": False, "output": f"[botnet ddos] Recharge — {_cd(state, 'botnet_ddos')} tick(s) restants."}
                    bonus = 35
                    state.cpu_cycles += bonus
                    state.suspicion = min(100, state.suspicion + 5.0)
                    _setcd(state, "botnet_ddos", 20)
                    return {
                        "ok": True,
                        "output": (
                            f"Attaque DDoS lancée depuis {state.infected_count} bots.\n"
                            f"Débit: {state.infected_count * 2.5} Gbps. Cible submergée. "
                            f"(+{bonus} CPU, méfiance +5%)"
                        ),
                    }
            return {"ok": False, "output": 'Syntaxe: botnet deploy <miners|ddos>'}

    # ── Commandes spécifiques TROJAN ─────────────────────────────
    if state.malware_class == "trojan":
        # msfvenom -p reverse_tcp
        if cmd == "msfvenom":
            flags = " ".join(args)
            if "-p" in flags and "reverse_tcp" in flags:
                if _cd(state, "msfvenom") > 0:
                    return {"ok": False, "output": f"[msfvenom] Recharge — {_cd(state, 'msfvenom')} tick(s) restants."}
                bonus = 20
                state.cpu_cycles += bonus
                _setcd(state, "msfvenom", 10)
                return {
                    "ok": True,
                    "output": (
                        f"Payload généré: windows/meterpreter/reverse_tcp\n"
                        f"  LHOST=10.0.0.{random.randint(1,254)} LPORT=4444\n"
                        f"  Taille: {random.randint(350,500)} bytes. Encodage shikata_ga_nai x3.\n"
                        f"  (+{bonus} CPU)"
                    ),
                }
            return {"ok": False, "output": 'Syntaxe: msfvenom -p reverse_tcp'}

        # mimikatz sekurlsa::logonpasswords
        if cmd == "mimikatz" and args and "sekurlsa::logonpasswords" in args[0].lower():
            if _cd(state, "mimikatz") > 0:
                return {"ok": False, "output": f"[mimikatz] Recharge — {_cd(state, 'mimikatz')} tick(s) restants."}
            bonus = 25
            state.cpu_cycles += bonus
            _setcd(state, "mimikatz", 12)
            return {
                "ok": True,
                "output": (
                    f"mimikatz # sekurlsa::logonpasswords\n"
                    f"  Authentication Id : 0 ; {random.randint(100000,999999)}\n"
                    f"  User Name         : Administrator\n"
                    f"  Domain            : CORP\n"
                    f"  NTLM              : {'{:032x}'.format(random.getrandbits(128))}\n"
                    f"  {random.randint(3, 8)} credentials extraits silencieusement. (+{bonus} CPU)"
                ),
            }

        # ssh -D 1080 pivot@target
        if cmd == "ssh" and "-D" in " ".join(args):
            flags = " ".join(args)
            if "1080" in flags:
                if _cd(state, "ssh_tunnel") > 0:
                    return {"ok": False, "output": f"[ssh tunnel] Recharge — {_cd(state, 'ssh_tunnel')} tick(s) restants."}
                bonus = 18
                state.cpu_cycles += bonus
                _setcd(state, "ssh_tunnel", 10)
                return {
                    "ok": True,
                    "output": (
                        f"Tunnel SOCKS5 ouvert sur 127.0.0.1:1080\n"
                        f"  Pivot actif via {state.infected_count} nœuds compromis.\n"
                        f"  Trafic routé de manière transparente. (+{bonus} CPU)"
                    ),
                }
            return {"ok": False, "output": 'Syntaxe: ssh -D 1080 pivot@target'}

        # exfil --dns --encode base64
        if cmd == "exfil":
            flags = " ".join(args)
            if "--dns" in flags and "--encode" in flags and "base64" in flags:
                if _cd(state, "exfil") > 0:
                    return {"ok": False, "output": f"[exfil] Recharge — {_cd(state, 'exfil')} tick(s) restants."}
                bonus = 30
                state.cpu_cycles += bonus
                state.suspicion = max(0, state.suspicion - 1.5)
                _setcd(state, "exfil", 12)
                return {
                    "ok": True,
                    "output": (
                        f"Exfiltration DNS en cours...\n"
                        f"  Données encodées en base64 et fragmentées en requêtes TXT.\n"
                        f"  {random.randint(50, 200)} Ko exfiltrés via dns.tunnel.corp.\n"
                        f"  Aucune alerte IDS déclenchée. (+{bonus} CPU, méfiance -1.5%)"
                    ),
                }
            return {"ok": False, "output": 'Syntaxe: exfil --dns --encode base64'}

    # ── Commandes spécifiques RANSOMWARE ─────────────────────────
    if state.malware_class == "ransomware":
        # encrypt --cipher aes-256-cbc
        if cmd == "encrypt":
            flags = " ".join(args)
            if "--cipher" in flags and "aes-256-cbc" in flags:
                if _cd(state, "encrypt") > 0:
                    return {"ok": False, "output": f"[encrypt] Recharge — {_cd(state, 'encrypt')} tick(s) restants."}
                bonus = 25
                state.cpu_cycles += bonus
                state.suspicion = min(100, state.suspicion + 4.0)
                _setcd(state, "encrypt", 12)
                return {
                    "ok": True,
                    "output": (
                        f"Chiffrement AES-256-CBC lancé sur {state.infected_count} machines...\n"
                        f"  {state.infected_count * random.randint(800, 2000)} fichiers chiffrés.\n"
                        f"  Clé RSA-4096 générée. (+{bonus} CPU, méfiance +4%)"
                    ),
                }
            return {"ok": False, "output": 'Syntaxe: encrypt --cipher aes-256-cbc'}

        # ransom --note DROP
        if cmd == "ransom":
            flags = " ".join(args)
            if "--note" in flags and "DROP" in raw:
                if _cd(state, "ransom_note") > 0:
                    return {"ok": False, "output": f"[ransom] Recharge — {_cd(state, 'ransom_note')} tick(s) restants."}
                bonus = 20
                state.cpu_cycles += bonus
                state.suspicion = min(100, state.suspicion + 2.0)
                _setcd(state, "ransom_note", 10)
                return {
                    "ok": True,
                    "output": (
                        f"Note de rançon déposée sur {state.infected_count} machines :\n"
                        f"  \"Vos fichiers ont été chiffrés. Payez 2.5 BTC pour récupérer vos données.\"\n"
                        f"  READ_ME.txt créé sur chaque bureau. (+{bonus} CPU, méfiance +2%)"
                    ),
                }
            return {"ok": False, "output": 'Syntaxe: ransom --note DROP'}

        # wmic shadowcopy delete
        if cmd == "wmic" and args and "shadowcopy" in " ".join(args).lower() and "delete" in " ".join(args).lower():
            if _cd(state, "wmic") > 0:
                return {"ok": False, "output": f"[wmic] Recharge — {_cd(state, 'wmic')} tick(s) restants."}
            bonus = 22
            state.cpu_cycles += bonus
            state.suspicion = min(100, state.suspicion + 3.5)
            _setcd(state, "wmic", 15)
            return {
                "ok": True,
                "output": (
                    f"Suppression des Volume Shadow Copies...\n"
                    f"  {random.randint(5, 15)} points de restauration détruits.\n"
                    f"  Récupération impossible sans clé. (+{bonus} CPU, méfiance +3.5%)"
                ),
            }

        # tor-negotiate --btc-wallet
        if raw.lower().startswith("tor-negotiate") and "--btc-wallet" in raw.lower():
            if _cd(state, "tor_negotiate") > 0:
                return {"ok": False, "output": f"[tor-negotiate] Recharge — {_cd(state, 'tor_negotiate')} tick(s) restants."}
            bonus = 35
            state.cpu_cycles += bonus
            state.suspicion = min(100, state.suspicion + 1.0)
            _setcd(state, "tor_negotiate", 20)
            return {
                "ok": True,
                "output": (
                    f"Connexion au réseau Tor établie...\n"
                    f"  Négociation avec la victime en cours via .onion\n"
                    f"  Wallet BTC: bc1q{'{:040x}'.format(random.getrandbits(160))[:40]}\n"
                    f"  Paiement partiel reçu. (+{bonus} CPU, méfiance +1%)"
                ),
            }

    # ── Commandes spécifiques ROOTKIT ────────────────────────────
    if state.malware_class == "rootkit":
        # insmod /dev/null/rootkit.ko
        if cmd == "insmod" and "/dev/null/rootkit.ko" in raw:
            if _cd(state, "insmod") > 0:
                return {"ok": False, "output": f"[insmod] Recharge — {_cd(state, 'insmod')} tick(s) restants."}
            bonus = 20
            state.cpu_cycles += bonus
            state.suspicion = max(0, state.suspicion - 2.0)
            _setcd(state, "insmod", 12)
            return {
                "ok": True,
                "output": (
                    f"Module noyau injecté: rootkit.ko\n"
                    f"  Hooks installés sur sys_read, sys_write, sys_getdents64.\n"
                    f"  Processus masqués au niveau kernel. (+{bonus} CPU, méfiance -2%)"
                ),
            }

        # syscall_hook --hide-pid
        if cmd == "syscall_hook" and "--hide-pid" in raw.lower():
            if _cd(state, "syscall_hook") > 0:
                return {"ok": False, "output": f"[syscall_hook] Recharge — {_cd(state, 'syscall_hook')} tick(s) restants."}
            bonus = 25
            state.cpu_cycles += bonus
            state.suspicion = max(0, state.suspicion - 3.0)
            _setcd(state, "syscall_hook", 15)
            return {
                "ok": True,
                "output": (
                    f"Hooks syscall installés avec succès.\n"
                    f"  PID du malware masqué dans /proc.\n"
                    f"  Invisible pour ps, top, htop et lsof. (+{bonus} CPU, méfiance -3%)"
                ),
            }

        # dd if=/dev/sda bs=512 count=1
        if cmd == "dd" and "/dev/sda" in raw:
            flags = " ".join(args)
            if "bs=512" in flags and "count=1" in flags:
                if _cd(state, "dd_mbr") > 0:
                    return {"ok": False, "output": f"[dd] Recharge — {_cd(state, 'dd_mbr')} tick(s) restants."}
                bonus = 22
                state.cpu_cycles += bonus
                state.suspicion = min(100, state.suspicion + 1.0)
                _setcd(state, "dd_mbr", 15)
                return {
                    "ok": True,
                    "output": (
                        f"MBR/UEFI infecté avec succès.\n"
                        f"  1+0 records in / 1+0 records out / 512 bytes copied\n"
                        f"  Persistance maximale : survit au reformatage. (+{bonus} CPU, méfiance +1%)"
                    ),
                }
            return {"ok": False, "output": 'Syntaxe: dd if=/dev/sda bs=512 count=1'}

        # ld_preload inject /lib/libhook.so
        if cmd == "ld_preload" and "inject" in raw.lower() and "/lib/libhook.so" in raw:
            if _cd(state, "ld_preload") > 0:
                return {"ok": False, "output": f"[ld_preload] Recharge — {_cd(state, 'ld_preload')} tick(s) restants."}
            bonus = 30
            state.cpu_cycles += bonus
            state.suspicion = max(0, state.suspicion - 2.5)
            _setcd(state, "ld_preload", 12)
            return {
                "ok": True,
                "output": (
                    f"LD_PRELOAD injection réussie : /lib/libhook.so\n"
                    f"  Toutes les applications chargent la bibliothèque compromise.\n"
                    f"  Interception transparente de toutes les fonctions libc. "
                    f"(+{bonus} CPU, méfiance -2.5%)"
                ),
            }

    # ── Hack spécial de classe ──────────────────────────────────────
    if cmd in ("hack", "special", "ability"):
        if state.special_cooldown > 0:
            return {
                "ok": False,
                "output": (
                    f"Hack special en recharge... ({state.special_cooldown} ticks restants)\n"
                    f"Tip : utilisez les commandes de base pour gagner du temps."
                ),
            }

        if state.malware_class == "worm":
            # Propagation massive : infecte jusqu'à 4 voisins directs
            candidates = [
                n for n in state.nodes
                if not n.infected and not n.quarantined and not n.honeypot
            ]
            targets = random.sample(candidates, min(4, len(candidates)))
            for n in targets:
                n.infected = True
            state.special_cooldown = 15
            state.suspicion = min(100.0, state.suspicion + 5.0)
            return {
                "ok": True,
                "output": (
                    f"[WORM] Propagation de masse activee !\n"
                    f"  {len(targets)} noeud(s) infecte(s) instantanement. (mefiance +5%, cooldown: 15 ticks)"
                ),
            }

        elif state.malware_class == "trojan":
            # Mode fantome : efface 25% de mefiance
            reduction = round(min(state.suspicion, 25.0), 1)
            state.suspicion = max(0.0, state.suspicion - reduction)
            state.special_cooldown = 20
            return {
                "ok": True,
                "output": (
                    f"[TROJAN] Mode fantome active !\n"
                    f"  Traces effacees. Mefiance -{reduction}%. (cooldown: 20 ticks)"
                ),
            }

        elif state.malware_class == "ransomware":
            # Rançon expresse : +200 CPU immédiatement
            bonus = 200
            state.cpu_cycles += bonus
            state.suspicion = min(100.0, state.suspicion + 8.0)
            state.special_cooldown = 25
            return {
                "ok": True,
                "output": (
                    f"[RANSOMWARE] Paiement force via crypto-mixer !\n"
                    f"  +{bonus} CPU Cycles. (mefiance +8%, cooldown: 25 ticks)"
                ),
            }

        elif state.malware_class == "rootkit":
            # Effacement total : mefiance remise à 0
            old_sus = round(state.suspicion, 1)
            state.suspicion = 0.0
            state.special_cooldown = 30
            return {
                "ok": True,
                "output": (
                    f"[ROOTKIT] Zero-trace execute !\n"
                    f"  Tous les logs systeme effaces. Mefiance {old_sus}% -> 0%. (cooldown: 30 ticks)"
                ),
            }

        return {"ok": False, "output": "Classe de malware inconnue."}

    # Upgrade par nom "symbolique"
    if cmd == "upgrade":
        if not args:
            return {"ok": False, "output": 'Syntaxe: upgrade <nom_amélioration>'}

        target = " ".join(args).lower()
        upgrades = get_all_upgrades()

        # Chercher par fragment de nom dans les upgrades du malware actuel
        found = None
        for u in upgrades:
            allowed = u["effect_json"].get("allowed_malware", [])
            if allowed and state.malware_class not in allowed:
                continue
            if target in u["name"].lower():
                found = u
                break

        if not found:
            return {"ok": False, "output": f"Aucune amélioration correspondant à '{target}' trouvée pour {state.malware_class}."}

        result = buy_upgrade(state, found["id"])
        if result.get("ok"):
            return {
                "ok": True,
                "output": f"Amélioration '{found['name']}' installée. CPU restants: {result['remaining_cycles']}.",
            }
        return {"ok": False, "output": result.get("error", "Achat impossible.")}

    # Log suspicion
    if cmd == "log" and args and args[0].lower() == "suspicion":
        return {
            "ok": True,
            "output": f"Jauge de méfiance: {round(state.suspicion, 1)}%. Patch déployé: {bool(state.patch_deployed)}.",
        }

    return {
        "ok": False,
        "output": f"Commande inconnue: {cmd}. Tapez 'help' pour la liste des commandes.",
    }


def buy_upgrade(state: GameState, upgrade_id: int) -> dict:
    """Achète une amélioration si le joueur a les ressources."""
    if upgrade_id in state.purchased_upgrades:
        return {"ok": False, "error": "Amélioration déjà achetée."}

    upgrades = get_all_upgrades()
    upgrade = next((u for u in upgrades if u["id"] == upgrade_id), None)
    if not upgrade:
        return {"ok": False, "error": "Amélioration inconnue."}

    # Vérifier que cette amélioration est disponible pour la classe de malware actuelle
    allowed = upgrade["effect_json"].get("allowed_malware")
    if allowed and state.malware_class not in allowed:
        return {"ok": False, "error": "Cette amélioration n'est pas compatible avec votre malware."}

    if state.cpu_cycles < upgrade["cost"]:
        return {"ok": False, "error": f"Pas assez de CPU Cycles ({upgrade['cost']} requis)."}

    # Vérifier le tier (il faut avoir acheté le tier précédent de la même branche, même malware)
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

    # Appliquer les effets
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
