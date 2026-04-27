"""
IA Blue Team — algorithme de décision défensive.

Stratégie par priorités pondérées :
  1. Scan léger périodique (visibilité réseau, faible coût)
  2. Honeypot positionnel : noeud sain maximisant les voisins infectés
  3. Quarantaine : noeud infecté maximisant le potentiel de propagation
  4. Patch anticipé si méfiance critique

Complexité par tick : O(N * deg_max) où N = nombre de noeuds.
"""

from server.game_state import GameState


class BlueTeamAI:

    COST_SCAN       = 15
    COST_HONEYPOT   = 30
    COST_QUARANTINE = 20
    COST_PATCH      = 50

    def decide(self, state: GameState) -> list[dict]:
        """Retourne la liste des actions à appliquer ce tick."""
        actions = []
        budget = state.it_budget

        # Scan périodique tous les 4 ticks
        if budget >= self.COST_SCAN and state.tick % 4 == 0:
            actions.append({"action": "scan"})
            budget -= self.COST_SCAN

        # Honeypot : un seul piège à la fois, positionné stratégiquement
        if not any(n.honeypot for n in state.nodes) and budget >= self.COST_HONEYPOT:
            target = self._best_honeypot_node(state)
            if target is not None:
                actions.append({"action": "honeypot", "node_id": target})
                budget -= self.COST_HONEYPOT

        # Quarantaine : isoler le noeud infecté le plus dangereux
        if state.suspicion >= 35 and budget >= self.COST_QUARANTINE:
            target = self._most_dangerous_infected(state)
            if target is not None:
                actions.append({"action": "quarantine", "node_id": target})
                budget -= self.COST_QUARANTINE

        # Patch anticipé si méfiance critique (avant 100%)
        if state.suspicion >= 82 and not state.patch_deployed and budget >= self.COST_PATCH:
            actions.append({"action": "patch"})

        return actions

    def _best_honeypot_node(self, state: GameState) -> int | None:
        """
        Choisit le noeud sain avec le plus de voisins infectés.
        Si aucun voisin infecté, prend le noeud le plus connecté (hub futur).
        """
        candidates = [
            n for n in state.nodes
            if not n.infected and not n.quarantined and not n.honeypot
        ]
        if not candidates:
            return None

        def neighbor_infected(node):
            return sum(1 for nid in node.connections if state.nodes[nid].infected)

        best = max(candidates, key=neighbor_infected)
        if neighbor_infected(best) == 0:
            return max(candidates, key=lambda n: len(n.connections)).id
        return best.id

    def _most_dangerous_infected(self, state: GameState) -> int | None:
        """
        Choisit le noeud infecté avec le plus grand nombre de voisins sains
        atteignables (potentiel de propagation maximal au prochain tick).
        """
        infected = [n for n in state.nodes if n.infected and not n.quarantined]
        if not infected:
            return None

        def spread_potential(node):
            return sum(
                1 for nid in node.connections
                if not state.nodes[nid].infected and not state.nodes[nid].quarantined
            )

        return max(infected, key=spread_potential).id
