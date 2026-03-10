# BLACKOUT

Jeu de stratégie en temps réel asynchrone — Projet Fil Rouge 2026, Ynov Campus Lille.

## Concept

Le joueur incarne un **malware** devant infecter un réseau cible avant d'être éradiqué par une intelligence artificielle de type **Blue Team**.

## Stack technique

| Couche | Technologie |
|--------|-------------|
| Front-end | HTML / CSS / JavaScript (vanilla) |
| Back-end | Python 3.12+ |
| Communication | WebSockets |
| Base de données | SQLite |

## Lancement rapide

```bash
# Installer les dépendances
pip install -r requirements.txt

# Démarrer le serveur
python -m server.main
```

Puis ouvrir `client/index.html` dans un navigateur (ou via http://localhost:8765 avec le serveur statique intégré).

## Structure du projet

```
├── server/
│   ├── main.py          # Point d'entrée WebSocket
│   ├── database.py      # Couche SQLite
│   ├── auth.py          # Authentification
│   ├── game_engine.py   # Moteur de jeu (tick)
│   └── game_state.py    # État de session
├── client/
│   ├── index.html
│   ├── css/style.css
│   └── js/
│       ├── main.js
│       ├── websocket.js
│       ├── auth.js
│       ├── game.js
│       ├── leaderboard.js
│       └── upgrades.js
└── requirements.txt
```

## Auteurs

Matéo DEFIEF, Alex MANFAIT, Lucie RÉMOND
