"""
Etat de session de jeu — topologie reseau, noeuds, infection, rooms duo.
"""

import json
import random
import math
from dataclasses import dataclass, field, asdict
from typing import Optional, Any


MALWARE_PROFILES = {
    "worm":       {"propagation": 0.20, "noise_per_machine": 1.5,  "income_per_node": 3.0, "start_infected": 2},
    "trojan":     {"propagation": 0.12, "noise_per_machine": 0.5,  "income_per_node": 3.5, "start_infected": 1},
    "ransomware": {"propagation": 0.14, "noise_per_machine": 2.2,  "income_per_node": 7.0, "start_infected": 1},
    "rootkit":    {"propagation": 0.06, "noise_per_machine": 0.15, "income_per_node": 2.5, "start_infected": 1},
}

# Zones disposées sur la carte (cx/cy en coordonnées canvas, r = rayon d'affichage)
ZONES_CONFIG = [
    {
        "id": 0, "name": "DMZ",   "label": "Zone Démilitarisée",
        "color": "#00ff88", "security": 1,
        "cx": 160, "cy": 330, "r": 125,
        "nodes": 5, "router": False, "sources": [],
    },
    {
        "id": 1, "name": "LAN",   "label": "Réseau Corporate",
        "color": "#00aaff", "security": 2,
        "cx": 450, "cy": 145, "r": 125,
        "nodes": 6, "router": True, "sources": [0],
    },
    {
        "id": 2, "name": "SRV",   "label": "Serveurs Internes",
        "color": "#ffaa00", "security": 3,
        "cx": 730, "cy": 285, "r": 115,
        "nodes": 5, "router": True, "sources": [1],
    },
    {
        "id": 3, "name": "DB",    "label": "Base de Données",
        "color": "#ff4444", "security": 4,
        "cx": 685, "cy": 525, "r": 105,
        "nodes": 4, "router": True, "sources": [2],
    },
    {
        "id": 4, "name": "SCADA", "label": "Infrastructure Critique",
        "color": "#dd00ff", "security": 5,
        "cx": 390, "cy": 545, "r": 105,
        "nodes": 3, "router": True, "sources": [0],
    },
]

# Probabilité par tick d'infecter un routeur selon son niveau de sécurité
ROUTER_INFECTION_CHANCE = {1: 0.25, 2: 0.16, 3: 0.10, 4: 0.06, 5: 0.03}


@dataclass
class Zone:
    id: int
    name: str
    label: str
    color: str
    security_level: int
    cx: float
    cy: float
    radius: float
    node_ids: list[int]
    router_id: Optional[int]
    unlocked: bool

    def to_dict(self):
        return asdict(self)


@dataclass
class Node:
    id: int
    x: float
    y: float
    infected: bool = False
    quarantined: bool = False
    honeypot: bool = False
    connections: list[int] = field(default_factory=list)
    zone_id: int = 0
    is_router: bool = False
    node_type: str = "workstation"  # "workstation" | "router"

    def to_dict(self):
        return asdict(self)


@dataclass
class Bubble:
    """Bulle cliquable sur la carte."""
    id: int
    x: float
    y: float
    kind: str   # "breach", "exfiltration" (Red), "log_analysis", "patch_deploy" (Blue)
    value: int
    ttl: int = 5

    def to_dict(self):
        return asdict(self)


@dataclass
class GameState:
    """Represente l'etat complet d'une partie (solo ou duo)."""
    party_id: Optional[int] = None
    user_id: int = 0
    malware_class: str = "worm"
    difficulty: str = "normal"
    mode: str = "solo"

    tick: int = 0
    nodes: list[Node] = field(default_factory=list)
    zones: list[Zone] = field(default_factory=list)
    total_nodes: int = 0

    # Ressources Red Team
    cpu_cycles: float = 50.0
    # Ressources Blue Team
    it_budget: float = 50.0

    suspicion: float = 0.0
    patch_deployed: bool = False
    clean_rate: float = 0.0

    purchased_upgrades: list[int] = field(default_factory=list)

    propagation_mod: float = 0.0
    stealth_mod: float = 0.0
    income_mod: float = 0.0
    passive_income_bonus: float = 0.0

    bubbles: list[Bubble] = field(default_factory=list)
    next_bubble_id: int = 1

    triggered_events: list[int] = field(default_factory=list)
    quarantine_last_tick: int = 0
    special_cooldown: int = 0
    command_cooldowns: dict = field(default_factory=dict)

    result: Optional[str] = None
    score: int = 0

    @property
    def infected_count(self) -> int:
        return sum(1 for n in self.nodes if n.infected and not n.quarantined)

    @property
    def healthy_count(self) -> int:
        return sum(1 for n in self.nodes if not n.infected and not n.quarantined)

    @property
    def quarantined_count(self) -> int:
        return sum(1 for n in self.nodes if n.quarantined)

    def to_dict(self) -> dict:
        return {
            "tick": self.tick,
            "malware_class": self.malware_class,
            "mode": self.mode,
            "nodes": [n.to_dict() for n in self.nodes],
            "zones": [z.to_dict() for z in self.zones],
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
            "special_cooldown": self.special_cooldown,
            "result": self.result,
            "score": self.score,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class DuoRoom:
    """Session de jeu en duo : Red Team vs Blue Team (humain ou IA)."""
    code: str
    state: GameState
    red_ws: Any
    blue_ws: Any = None
    blue_is_ai: bool = False
    red_user: dict = field(default_factory=dict)
    blue_user: dict = field(default_factory=dict)


def generate_zone_topology() -> tuple[list, list]:
    """
    Génère un graphe réseau organisé en zones distinctes.
    Chaque zone (sauf DMZ) est protégée par un routeur que le joueur doit infecter
    pour débloquer l'accès aux machines internes.
    """
    nodes: list[Node] = []
    zones: list[Zone] = []
    node_id = 0

    for zconf in ZONES_CONFIG:
        zone_node_ids: list[int] = []
        router_id: Optional[int] = None

        # Noeuds réguliers disposés en cercle autour du centre de la zone
        n = zconf["nodes"]
        inner_r = zconf["r"] * 0.55
        for i in range(n):
            angle = (2 * math.pi * i / n) + random.uniform(-0.15, 0.15)
            r = inner_r * random.uniform(0.65, 1.0)
            x = round(zconf["cx"] + r * math.cos(angle), 1)
            y = round(zconf["cy"] + r * math.sin(angle), 1)
            node = Node(id=node_id, x=x, y=y,
                        zone_id=zconf["id"], is_router=False, node_type="workstation")
            nodes.append(node)
            zone_node_ids.append(node_id)
            node_id += 1

        # Routeur placé à la bordure de la zone, orienté vers la zone source
        if zconf["router"]:
            if zconf["sources"]:
                src = ZONES_CONFIG[zconf["sources"][0]]
                angle = math.atan2(src["cy"] - zconf["cy"], src["cx"] - zconf["cx"])
            else:
                angle = 0.0
            rx = round(zconf["cx"] + zconf["r"] * 0.88 * math.cos(angle), 1)
            ry = round(zconf["cy"] + zconf["r"] * 0.88 * math.sin(angle), 1)
            router = Node(id=node_id, x=rx, y=ry,
                          zone_id=zconf["id"], is_router=True, node_type="router")
            nodes.append(router)
            zone_node_ids.append(node_id)
            router_id = node_id
            node_id += 1

        # Connexions internes : anneau de base garantissant la connectivité
        for i in range(len(zone_node_ids)):
            a = zone_node_ids[i]
            b = zone_node_ids[(i + 1) % len(zone_node_ids)]
            if b not in nodes[a].connections:
                nodes[a].connections.append(b)
                nodes[b].connections.append(a)

        # Arêtes supplémentaires internes (~25% de densité)
        for i in range(len(zone_node_ids)):
            for j in range(i + 2, len(zone_node_ids)):
                if random.random() < 0.25:
                    a, b = zone_node_ids[i], zone_node_ids[j]
                    if b not in nodes[a].connections:
                        nodes[a].connections.append(b)
                        nodes[b].connections.append(a)

        zone = Zone(
            id=zconf["id"],
            name=zconf["name"],
            label=zconf["label"],
            color=zconf["color"],
            security_level=zconf["security"],
            cx=zconf["cx"],
            cy=zconf["cy"],
            radius=zconf["r"],
            node_ids=zone_node_ids,
            router_id=router_id,
            unlocked=not zconf["router"],  # DMZ toujours déverrouillée dès le départ
        )
        zones.append(zone)

    # Connexions inter-zones : chaque routeur est relié à des noeuds de sa zone source
    for zconf in ZONES_CONFIG:
        if not zconf["router"] or not zconf["sources"]:
            continue
        zone = zones[zconf["id"]]
        router_node = nodes[zone.router_id]
        for src_id in zconf["sources"]:
            src_zone = zones[src_id]
            src_regulars = [nid for nid in src_zone.node_ids if not nodes[nid].is_router]
            for nid in random.sample(src_regulars, min(2, len(src_regulars))):
                if nid not in router_node.connections:
                    router_node.connections.append(nid)
                    nodes[nid].connections.append(router_node.id)

    return nodes, zones


def create_new_game(user_id: int, malware_class: str, num_nodes: int = 30, mode: str = "solo") -> GameState:
    """Initialise une nouvelle partie avec topologie par zones."""
    profile = MALWARE_PROFILES.get(malware_class, MALWARE_PROFILES["worm"])
    nodes, zones = generate_zone_topology()
    total = len(nodes)

    state = GameState(
        user_id=user_id,
        malware_class=malware_class,
        total_nodes=total,
        nodes=nodes,
        zones=zones,
        mode=mode,
    )

    # Infection initiale dans la DMZ, sur des noeuds réguliers uniquement
    dmz_zone = zones[0]
    dmz_regular = [nid for nid in dmz_zone.node_ids if not nodes[nid].is_router]
    start_count = min(profile["start_infected"], len(dmz_regular))
    for idx in random.sample(dmz_regular, start_count):
        state.nodes[idx].infected = True

    return state
