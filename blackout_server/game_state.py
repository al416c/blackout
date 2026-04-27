"""
État de session de jeu — gère la topologie réseau, les nœuds, l'infection, etc.
"""
import json
import random
import math
from dataclasses import dataclass, field, asdict
from typing import Optional

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
    sector_id: int = 0
    sector_name: str = "SEC_0x00"
    sector_color: str = "#ffffff"
    is_gateway: bool = False

    def to_dict(self):
        return asdict(self)

@dataclass
class Bubble:
    id: int
    x: float
    y: float
    kind: str
    value: int
    ttl: int = 5
    def to_dict(self):
        return asdict(self)

@dataclass
class GameState:
    party_id: Optional[int] = None
    user_id: int = 0
    malware_class: str = "worm"
    difficulty: str = "normal"
    tick: int = 0
    nodes: list[Node] = field(default_factory=list)
    total_nodes: int = 0
    cpu_cycles: float = 50.0
    it_budget: float = 50.0
    suspicion: float = 0.0
    patch_deployed: bool = False
    clean_rate: float = 0.0
    purchased_upgrades: list[int] = field(default_factory=list)
    propagation_mod: float = 0.0
    stealth_mod: float = 0.0
    income_mod: float = 0.0
    passive_income_bonus: float = 0.0
    porosity_mod: float = 0.0
    gateway_discount: float = 0.0
    reveal_sectors: bool = False
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

    def to_dict(self) -> dict:
        return {
            "tick": self.tick,
            "malware_class": self.malware_class,
            "nodes": [n.to_dict() for n in self.nodes],
            "total_nodes": self.total_nodes,
            "infected_count": self.infected_count,
            "healthy_count": self.healthy_count,
            "cpu_cycles": round(self.cpu_cycles, 1),
            "suspicion": round(self.suspicion, 2),
            "purchased_upgrades": self.purchased_upgrades,
            "bubbles": [b.to_dict() for b in self.bubbles],
            "result": self.result,
            "score": self.score,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

def generate_network(num_sectors: int = 17) -> list[Node]:
    nodes = []
    sector_centers = []
    NEON_COLORS = ["#8a4fff", "#00f2ff", "#00ff99", "#ff0055", "#ff9900", "#ffcc00", "#4488ff", "#ff44cc"]
    for i in range(num_sectors):
        sector_centers.append((random.uniform(200, 3300), random.uniform(200, 2300)))
    
    node_id_counter = 0
    gateways = {}
    for s_id, (cx, cy) in enumerate(sector_centers):
        num = random.randint(4, 7)
        color = NEON_COLORS[s_id % len(NEON_COLORS)]
        sector_nodes = []
        for j in range(num):
            node = Node(
                id=node_id_counter, 
                x=round(cx + random.uniform(-150, 150), 1),
                y=round(cy + random.uniform(-150, 150), 1),
                sector_id=s_id,
                sector_name=f"SEC_0x{s_id:02X}",
                sector_color=color,
                is_gateway=(j == 0)
            )
            nodes.append(node)
            sector_nodes.append(node)
            if node.is_gateway:
                gateways[s_id] = node
            node_id_counter += 1
        
        for k in range(len(sector_nodes)):
            for l in range(k + 1, len(sector_nodes)):
                if random.random() < 0.6:
                    sector_nodes[k].connections.append(sector_nodes[l].id)
                    sector_nodes[l].connections.append(sector_nodes[k].id)
    
    for s_id, gw in gateways.items():
        others = sorted([ogw for oid, ogw in gateways.items() if oid != s_id], 
                        key=lambda o: math.hypot(gw.x - o.x, gw.y - o.y))
        for neighbor in others[:2]:
            if neighbor.id not in gw.connections:
                gw.connections.append(neighbor.id)
                neighbor.connections.append(gw.id)
    return nodes

def create_new_game(user_id: int, malware_class: str, num_nodes: int = 100) -> GameState:
    profile = MALWARE_PROFILES.get(malware_class, MALWARE_PROFILES["worm"])
    nodes = generate_network(17)
    state = GameState(user_id=user_id, malware_class=malware_class, total_nodes=len(nodes), nodes=nodes)
    start_indices = random.sample(range(len(nodes)), profile["start_infected"])
    for idx in start_indices:
        state.nodes[idx].infected = True
    return state
