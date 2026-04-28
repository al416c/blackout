# BLACKOUT

Jeu de cybersécurité en temps réel (Red Team vs Blue Team) — Projet Fil Rouge 2026, Ynov Campus Lille.

**Auteurs :** Matéo DEFIEF, Alex MANFAIT, Lucie RÉMOND

---

## Stack technique

| Couche | Technologie |
|--------|-------------|
| Front-end | HTML / CSS / JavaScript vanilla |
| Back-end | Python 3.12+ (asyncio + websockets) |
| Communication | WebSockets |
| Base de données | SQLite |

---

## Lancer le jeu

```bash
# Créer et activer l'environnement virtuel
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

# Installer les dépendances
pip install websockets

# Lancer le serveur
python -m server.main
```

Ouvrir `http://localhost:8765` dans le navigateur.

---

## Concept

Le joueur incarne la **Red Team** (attaquant) : un malware qui doit infecter l'intégralité d'un réseau d'entreprise avant que la **Blue Team** (défenseur, humain ou IA) ne le détecte et l'éradique.

Le réseau est divisé en **5 zones** de sécurité croissante. Chaque zone sauf la DMZ est verrouillée par un **routeur** qu'il faut infecter pour débloquer l'accès aux machines internes.

---

## Zones réseau

| Zone  | Nom complet              | Sécurité | Nœuds | Chance de crack/tick |
|-------|--------------------------|----------|-------|----------------------|
| DMZ   | Zone Démilitarisée       | 1        | 14    | Zone de départ       |
| LAN   | Réseau Corporate         | 2        | 16+1  | ~16%                 |
| SRV   | Serveurs Internes        | 3        | 13+1  | ~10%                 |
| DB    | Base de Données          | 4        | 10+1  | ~6%                  |
| SCADA | Infrastructure Critique  | 5        | 9+1   | ~3%                  |

Une zone verrouillée n'est visible que par son routeur (carré rouge). Infecter le routeur déverrouille automatiquement la zone entière.

---

## Ressources

**Red Team — CPU Cycles**
- Gagnés passivement à chaque tick (proportionnel aux nœuds infectés)
- Gagnés en cliquant les bulles rouges/orange (Breach, Exfiltration)
- Gagnés via les commandes du terminal
- Utilisés pour acheter des améliorations dans le panneau de droite

**Blue Team — IT Budget**
- Se régénère passivement chaque tick (proportionnel aux nœuds sains)
- Gagné en cliquant les bulles bleues/cyan (Log Analysis, Patch Deploy)
- Utilisé pour les actions défensives (scan, honeypot, quarantaine, patch)

---

## Barre de méfiance (Suspicion)

Chaque nœud infecté génère du bruit réseau. Plus il y a de nœuds infectés, plus la méfiance monte vite. À **100%**, la Blue Team déploie un patch automatique qui commence à nettoyer le réseau.

Des événements automatiques se déclenchent à 30%, 50%, 70% de méfiance (honeypots, quarantaines, pénalités de propagation).

---

## Classes de malware

| Classe     | Propagation | Bruit       | Revenus     | Style         |
|------------|-------------|-------------|-------------|---------------|
| Worm       | 0.20 (rapide)| Élevé      | Moyen       | Aggro         |
| Trojan     | 0.12        | Faible      | Moyen+      | Infiltration  |
| Ransomware | 0.14        | Très élevé  | Très élevé  | Force brute   |
| Rootkit    | 0.06 (lent) | Très faible | Moyen       | Furtivité     |

---

## Modes de jeu

### Solo vs IA
Le joueur est la Red Team. La Blue Team est contrôlée par l'IA qui scanne périodiquement, pose des honeypots stratégiques, quarantaine les nœuds dangereux et déploie le patch en urgence.

### Duo (humain vs humain)
Deux joueurs s'affrontent en temps réel. Le créateur de la partie est la **Red Team**, celui qui rejoint est la **Blue Team**.

- Partager le code de salle à 6 caractères affiché dans l'overlay
- Chaque équipe a ses propres commandes de terminal

---

## Terminal — Red Team

| Commande               | Effet                                    |
|------------------------|------------------------------------------|
| `help`                 | Liste toutes les commandes disponibles   |
| `status`               | Résumé de l'état du malware              |
| `zones`                | État de toutes les zones réseau          |
| `hack`                 | Capacité spéciale de la classe (cooldown)|
| `nmap -A -sV`          | Scan agressif (+10 CPU, cd 6t)           |
| `nmap -sS -T4 -Pn`     | Scan furtif (méfiance -2%, cd 8t)        |
| `phishing start`       | Campagne de phishing (+CPU, cd 10t)      |
| `ps aux`               | Processus actifs (+3 CPU, cd 6t)         |
| `cat /etc/shadow`      | Extraction de hash (+15 CPU, cd 12t)     |
| `tcpdump -i eth0 -nn`  | Capture réseau (+12 CPU, cd 10t)         |
| `ifconfig`             | Infos réseau                             |
| `whoami`               | Identité du malware                      |
| `log suspicion`        | Niveau de méfiance actuel                |
| `upgrade <nom>`        | Acheter une amélioration par son nom     |

Commandes supplémentaires selon la classe sélectionnée (voir `help` en jeu).

### Capacités spéciales (`hack`)
- **Worm** : infecte 4 nœuds instantanément (cd 15t)
- **Trojan** : réduit la méfiance de 25% (cd 20t)
- **Ransomware** : force un paiement +200 CPU (cd 25t)
- **Rootkit** : remet la méfiance à 0% (cd 30t)

---

## Terminal — Blue Team (mode duo uniquement)

| Commande              | Coût IT | Effet                                          |
|-----------------------|---------|------------------------------------------------|
| `help`                | —       | Liste toutes les commandes défensives          |
| `status`              | —       | État du réseau et budget IT                    |
| `audit`               | —       | Rapport détaillé de toutes les zones           |
| `scan`                | 15 IT   | Révèle les nœuds infectés (cd 4t)              |
| `honeypot <id>`       | 30 IT   | Piège sur un nœud sain                         |
| `quarantine <id>`     | 20 IT   | Isole un nœud infecté                          |
| `patch`               | 50 IT   | Déploie le patch global (nettoie le réseau)    |
| `firewall <id>`       | 25 IT   | Protège un nœud contre l'infection (10 ticks)  |
| `isolate <zone>`      | 30 IT   | Quarantaine de tous les infectés d'une zone    |
| `analyze <id>`        | —       | Analyse les connexions d'un nœud               |
| `log suspicion`       | —       | Niveau de méfiance actuel                      |

---

## Améliorations (panneau de droite — Red Team)

Trois branches d'améliorations à débloquer progressivement avec les CPU Cycles :

- **Transmission** : améliore la propagation du malware
- **Symptômes** : réduit la génération de bruit (furtivité)
- **Capacités** : augmente les revenus passifs

Certaines améliorations sont réservées à des classes spécifiques.

---

## Bulles cliquables

Des bulles apparaissent aléatoirement sur la carte près des nœuds infectés :

| Bulle          | Couleur | Red Team    | Blue Team   |
|----------------|---------|-------------|-------------|
| Breach         | Violet  | +CPU Cycles | Ignorée     |
| Exfiltration   | Violet  | +CPU Cycles | Ignorée     |
| Log Analysis   | Cyan    | +Méfiance   | +IT Budget  |
| Patch Deploy   | Cyan    | +Méfiance   | +IT Budget  |

---

## Conditions de victoire/défaite

**Red Team gagne** : 100% des nœuds infectés (aucun nœud sain ni en quarantaine)  
**Blue Team gagne** : Le malware est entièrement éradiqué (0 nœud infecté)

---

## Structure du projet

```
blackout/
├── server/
│   ├── main.py          # Serveur WebSocket + HTTP statique
│   ├── game_state.py    # Dataclasses : GameState, Node, Zone, DuoRoom
│   ├── game_engine.py   # Logique de tick, commandes terminal, upgrades
│   ├── blue_team_ai.py  # IA Blue Team
│   ├── auth.py          # Authentification
│   └── database.py      # SQLite : users, parties, upgrades, events
└── client/
    ├── index.html
    ├── js/
    │   ├── websocket.js  # Couche WebSocket
    │   ├── game.js       # Canvas 2D (rendu zones, nœuds, bulles)
    │   ├── terminal.js   # Terminal de commandes
    │   ├── main.js       # Orchestration, rôles, navigation
    │   ├── auth.js       # Formulaires login/register
    │   ├── upgrades.js   # Panneau d'améliorations
    │   └── particles.js  # Effet de fond
    └── css/
```
