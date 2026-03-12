"""
Moteur de jeu BLACKOUT — exécute la logique de chaque tick.

Algorithmes du cahier des charges :
  Propagation : N_inf = M_inf × (T_inf + M_mod) × (M_saines / M_totales)
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
    profile = MALWARE_PROFILES[state.malware_class]

    m_inf = state.infected_count
    m_saines = state.healthy_count
    m_totales = state.total_nodes

    if m_totales == 0:
        return state

    # ── Modificateurs de difficulté ──────────────────────────────
    diff = (state.difficulty or "normal").lower()
    if diff == "facile":
        suspicion_mult = 0.7
        income_mult = 1.2
    elif diff == "difficile":
        suspicion_mult = 1.25
        income_mult = 0.9
    else:
        suspicion_mult = 1.0
        income_mult = 1.0

    # ── 1. Propagation ───────────────────────────────────────────
    t_inf = profile["propagation"]
    m_mod = state.propagation_mod
    ratio = m_saines / m_totales if m_totales > 0 else 0

    n_inf = m_inf * (t_inf + m_mod) * ratio
    new_infections = max(0, round(n_inf))

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
    income = profile["income_per_node"]
    state.cpu_cycles += state.infected_count * (income + state.income_mod) * 0.5 * income_mult
    state.cpu_cycles += state.passive_income_bonus

    # Blue Team budget
    state.it_budget += state.healthy_count * 0.3

    # ── 3. Bruit & Méfiance ─────────────────────────────────────
    b_machine = profile["noise_per_machine"]
    stealth_factor = max(0.05, 1.0 - state.stealth_mod)
    b_total = state.infected_count * b_machine * stealth_factor

    # Légère réduction du gain de méfiance par tick pour laisser
    # plus de temps au joueur avant le déploiement du patch,
    # modulée par la difficulté.
    suspicion_increase = b_total * 0.2 * suspicion_mult
    state.suspicion = min(100.0, state.suspicion + suspicion_increase)

    # ── 4. Événements Blue Team ──────────────────────────────────
    blue_events = get_blueteam_events()
    for event in blue_events:
        if state.suspicion >= event["trigger_threshold"]:
            effect = event["effect_json"]

            # Honeypot
            if effect.get("trap_node") and not any(n.honeypot for n in state.nodes):
                healthy_nodes = [n for n in state.nodes if not n.infected and not n.quarantined]
                if healthy_nodes:
                    trap = random.choice(healthy_nodes)
                    trap.honeypot = True

            # Quarantaine (air gap)
            if effect.get("quarantine"):
                infected_nodes = [n for n in state.nodes if n.infected and not n.quarantined]
                if infected_nodes:
                    iso_count = max(1, int(len(infected_nodes) * effect.get("isolation_rate", 0.1)))
                    to_quarantine = random.sample(infected_nodes, min(iso_count, len(infected_nodes)))
                    for node in to_quarantine:
                        node.quarantined = True

            # Réduction propagation
            if "propagation_penalty" in effect:
                state.propagation_mod += effect["propagation_penalty"]

            # Détection → augmente encore la méfiance
            if "detection_rate" in effect:
                state.suspicion = min(100.0, state.suspicion + effect["detection_rate"] * 7)

    # ── 5. Patch de sécurité (méfiance = 100%) ──────────────────
    if state.suspicion >= 100.0 and not state.patch_deployed:
        state.patch_deployed = True
        # Patch légèrement plus efficace pour que la fin de partie
        # soit plus tranchée une fois la Blue Team pleinement alertée.
        state.clean_rate = 0.18

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
    """Fait apparaître des bulles cliquables aléatoirement."""
    # Bulles attaquant
    if random.random() < 0.25:
        kind = random.choice(["breach", "exfiltration"])
        value = random.randint(10, 30)
        x = random.uniform(50, 850)
        y = random.uniform(50, 650)
        state.bubbles.append(Bubble(
            id=state.next_bubble_id, x=round(x, 1), y=round(y, 1),
            kind=kind, value=value, ttl=6,
        ))
        state.next_bubble_id += 1

    # Bulles défenseur
    if random.random() < 0.20:
        kind = random.choice(["log_analysis", "patch_deploy"])
        value = random.randint(5, 20)
        x = random.uniform(50, 850)
        y = random.uniform(50, 650)
        state.bubbles.append(Bubble(
            id=state.next_bubble_id, x=round(x, 1), y=round(y, 1),
            kind=kind, value=value, ttl=6,
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
                # Bulles Blue Team moins punitives pour garder un rythme agréable.
                suspicion_delta = b.value * 0.35
                state.suspicion = min(100.0, state.suspicion + suspicion_delta)
                feedback = {"type": "defender", "kind": b.kind, "suspicion_added": suspicion_delta}
            state.bubbles.pop(i)
            return feedback
    return {"error": "Bulle introuvable."}


def execute_command(state: GameState, line: str) -> dict:
    """
    Interprète une ligne de commande du terminal.
    Les commandes sont volontairement simples et "dans l'ambiance" hacking,
    mais mappent sur des actions de gameplay existantes.
    """
    raw = (line or "").strip()
    if not raw:
        return {"ok": False, "output": "Aucune commande saisie."}

    tokens = raw.split()
    cmd = tokens[0].lower()
    args = tokens[1:]

    # Aide
    if cmd in ("help", "aide", "?"):
        return {
            "ok": True,
            "output": (
                "Commandes disponibles :\n"
                "  help                — Affiche cette aide.\n"
                "  status              — Résumé de l'état du malware.\n"
                "  nmap -A -sV         — Scan agressif du réseau (petit bonus de ressources).\n"
                "  phishing start      — Lance une campagne de phishing (bonus CPU).\n"
                "  upgrade phishing    — Tente d'acheter l'upgrade 'Phishing' (Transmission).\n"
                "  upgrade crypto      — Tente d'acheter 'Cryptomineur' (Symptômes).\n"
                "  log suspicion       — Affiche la jauge de méfiance actuelle."
            ),
        }

    # Statut rapide
    if cmd in ("status", "statut"):
        msg = (
            f"Tick: {state.tick} | Malware: {state.malware_class} | "
            f"Nœuds infectés: {state.infected_count}/{state.total_nodes} | "
            f"CPU: {int(state.cpu_cycles)} | Méfiance: {round(state.suspicion, 1)}%"
        )
        return {"ok": True, "output": msg}

    # nmap / scan réseau — ambiance recon / petit bonus
    if cmd == "nmap" or cmd == "scan":
        flags = " ".join(args)
        bonus = 5
        if "-A" in flags and "-sV" in flags:
            bonus = 10
        state.cpu_cycles += bonus
        return {
            "ok": True,
            "output": (
                f"Scan réseau terminé ({flags or 'mode par défaut'}). "
                f"Nouvelles surfaces d'attaque identifiées (+{bonus} CPU Cycles)."
            ),
        }

    # Campagne de phishing — simple bonus de ressources
    if cmd == "phishing":
        if args and args[0].lower() == "start":
            gain = max(8, int(state.infected_count * 1.5) or 8)
            state.cpu_cycles += gain
            return {
                "ok": True,
                "output": f"Campagne de phishing lancée. Plusieurs utilisateurs ont cliqué... (+{gain} CPU Cycles)",
            }
        return {
            "ok": False,
            "output": 'Syntaxe: "phishing start"',
        }

    # Upgrade par nom "symbolique"
    if cmd == "upgrade":
        if not args:
            return {"ok": False, "output": 'Syntaxe: upgrade [phishing|crypto]'}

        target = args[0].lower()
        upgrades = get_all_upgrades()

        def find_by_name_fragment(fragment: str):
            for u in upgrades:
                if fragment in u["name"].lower():
                    return u
            return None

        if target == "phishing":
            up = find_by_name_fragment("phishing")
        elif target in ("crypto", "cryptomineur"):
            up = find_by_name_fragment("cryptomineur")
        else:
            up = None

        if not up:
            return {"ok": False, "output": "Aucune amélioration correspondante trouvée."}

        result = buy_upgrade(state, up["id"])
        if result.get("ok"):
            return {
                "ok": True,
                "output": f"Amélioration '{up['name']}' installée. CPU restants: {result['remaining_cycles']}.",
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

    # Vérifier le tier (il faut avoir acheté le tier précédent de la même branche)
    if upgrade["tier"] > 1:
        same_branch = [u for u in upgrades if u["branch"] == upgrade["branch"] and u["tier"] == upgrade["tier"] - 1]
        if same_branch and same_branch[0]["id"] not in state.purchased_upgrades:
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
