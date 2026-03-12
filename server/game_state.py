"""
État de session de jeu — gère la topologie réseau, les nœuds, l'infection, etc.
"""

import json
import random
import math
from dataclasses import dataclass, field, asdict
from typing import Optional


# ── Constantes par classe de malware ─────────────────────────────────
#
# Ces valeurs sont légèrement plus généreuses en revenus et un peu moins
# agressives en bruit pour rendre les parties plus dynamiques et lisibles.

MALWARE_PROFILES = {
    "worm":       {"propagation": 0.20, "noise_per_machine": 1.5, "income_per_node": 3.0, "start_infected": 2},
    "trojan":     {"propagation": 0.12, "noise_per_machine": 0.5, "income_per_node": 3.5, "start_infected": 1},
    "ransomware": {"propagation": 0.14, "noise_per_machine": 2.2, "income_per_node": 7.0, "start_infected": 1},
    "rootkit":    {"propagation": 0.06, "noise_per_machine": 0.15, "income_per_node": 2.5, "start_infected": 1},
}


@dataclass
class Node:
    id: int
    x: float
    y: float
    infected: bool = False
    quarantined: bool = False
    honeypot: bool = False
    connections: list[int] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


@dataclass
class Bubble:
    """Bulle cliquable sur la carte."""
    id: int
    x: float
    y: float
    kind: str           # "breach" (rouge), "exfiltration" (orange), "log_analysis" (bleu), "patch_deploy" (vert)
    value: int
    ttl: int = 5        # ticks restants avant disparition

    def to_dict(self):
        return asdict(self)


@dataclass
class GameState:
    """Représente l'état complet d'une partie."""
    party_id: Optional[int] = None
    user_id: int = 0
    malware_class: str = "worm"
    difficulty: str = "normal"  # "facile" | "normal" | "difficile"

    tick: int = 0
    nodes: list[Node] = field(default_factory=list)
    total_nodes: int = 0

    # Ressources joueur
    cpu_cycles: float = 50.0
    # Ressources Blue Team
    it_budget: float = 50.0

    # Méfiance (0 – 100)
    suspicion: float = 0.0
    patch_deployed: bool = False
    clean_rate: float = 0.0

    # Upgrades achetées (ids)
    purchased_upgrades: list[int] = field(default_factory=list)

    # Modificateurs cumulés
    propagation_mod: float = 0.0
    stealth_mod: float = 0.0
    income_mod: float = 0.0
    passive_income_bonus: float = 0.0

    # Bulles actives
    bubbles: list[Bubble] = field(default_factory=list)
    next_bubble_id: int = 1

    # Résultat
    result: Optional[str] = None   # "victory" | "defeat"
    score: int = 0

    # ── Compteurs dérivés ────────────────────────────────────────
    @property
    def infected_count(self) -> int:
        return sum(1 for n in self.nodes if n.infected and not n.quarantined)

    @property
    def healthy_count(self) -> int:
        return sum(1 for n in self.nodes if not n.infected and not n.quarantined)

    @property
    def quarantined_count(self) -> int:
        return sum(1 for n in self.nodes if n.quarantined)

    # ── Sérialisation ────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "tick": self.tick,
            "malware_class": self.malware_class,
            "nodes": [n.to_dict() for n in self.nodes],
            "total_nodes": self.total_nodes,
            "infected_count": self.infected_count,
            "healthy_count": self.healthy_count,
            "quarantined_count": self.quarantined_count,
            "cpu_cycles": round(self.cpu_cycles, 1),
            "it_budget": round(self.it_budget, 1),
            "suspicion": round(self.suspicion, 2),
            "patch_deployed": self.patch_deployed,
            "purchased_upgrades": self.purchased_upgrades,
            "bubbles": [b.to_dict() for b in self.bubbles],
            "result": self.result,
            "score": self.score,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


# ── Génération de la topologie réseau ────────────────────────────────

def generate_network(num_nodes: int = 30, connection_chance: float = 0.15) -> list[Node]:
    """Génère un graphe de réseau aléatoire avec positions 2D."""
    nodes: list[Node] = []
    for i in range(num_nodes):
        angle = 2 * math.pi * i / num_nodes
        radius = 300 + random.uniform(-60, 60)
        x = 450 + radius * math.cos(angle)
        y = 350 + radius * math.sin(angle)
        nodes.append(Node(id=i, x=round(x, 1), y=round(y, 1)))

    # Assurer la connexité : chaîne minimum
    indices = list(range(num_nodes))
    random.shuffle(indices)
    for k in range(len(indices) - 1):
        a, b = indices[k], indices[k + 1]
        nodes[a].connections.append(b)
        nodes[b].connections.append(a)

    # Ajouter des arêtes supplémentaires
    for i in range(num_nodes):
        for j in range(i + 1, num_nodes):
            if j not in nodes[i].connections and random.random() < connection_chance:
                nodes[i].connections.append(j)
                nodes[j].connections.append(i)

    return nodes


def create_new_game(user_id: int, malware_class: str, num_nodes: int = 30) -> GameState:
    """Initialise une nouvelle partie."""
    profile = MALWARE_PROFILES.get(malware_class, MALWARE_PROFILES["worm"])
    nodes = generate_network(num_nodes)

    state = GameState(
        user_id=user_id,
        malware_class=malware_class,
        total_nodes=num_nodes,
        nodes=nodes,
    )

    # Infecter les nœuds de départ
    start_indices = random.sample(range(num_nodes), min(profile["start_infected"], num_nodes))
    for idx in start_indices:
        state.nodes[idx].infected = True

    return state
