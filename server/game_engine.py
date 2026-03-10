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
    state.cpu_cycles += state.infected_count * (income + state.income_mod) * 0.5
    state.cpu_cycles += state.passive_income_bonus

    # Blue Team budget
    state.it_budget += state.healthy_count * 0.3

    # ── 3. Bruit & Méfiance ─────────────────────────────────────
    b_machine = profile["noise_per_machine"]
    stealth_factor = max(0.05, 1.0 - state.stealth_mod)
    b_total = state.infected_count * b_machine * stealth_factor

    suspicion_increase = b_total * 0.3
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
                state.suspicion = min(100.0, state.suspicion + effect["detection_rate"] * 10)

    # ── 5. Patch de sécurité (méfiance = 100%) ──────────────────
    if state.suspicion >= 100.0 and not state.patch_deployed:
        state.patch_deployed = True
        state.clean_rate = 0.15

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
                state.suspicion = min(100.0, state.suspicion + b.value * 0.5)
                feedback = {"type": "defender", "kind": b.kind, "suspicion_added": b.value * 0.5}
            state.bubbles.pop(i)
            return feedback
    return {"error": "Bulle introuvable."}


def buy_upgrade(state: GameState, upgrade_id: int) -> dict:
    """Achète une amélioration si le joueur a les ressources."""
    if upgrade_id in state.purchased_upgrades:
        return {"ok": False, "error": "Amélioration déjà achetée."}

    upgrades = get_all_upgrades()
    upgrade = next((u for u in upgrades if u["id"] == upgrade_id), None)
    if not upgrade:
        return {"ok": False, "error": "Amélioration inconnue."}

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
