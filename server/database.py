"""
Couche de persistance SQLite pour BLACKOUT.
Tables : users, upgrade, blueteam, parties.
"""

import sqlite3
import os
import json
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "blackout.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Crée les tables si elles n'existent pas et insère les données de référence."""
    conn = get_connection()
    cur = conn.cursor()

    # ── Table users ──────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    UNIQUE NOT NULL,
            password_hash TEXT    NOT NULL,
            games_played  INTEGER DEFAULT 0,
            games_won     INTEGER DEFAULT 0,
            best_score    INTEGER DEFAULT 0,
            total_nodes   INTEGER DEFAULT 0,
            created_at    TEXT    DEFAULT (datetime('now'))
        )
    """)

    # ── Table upgrade ────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS upgrade (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            branch      TEXT    NOT NULL CHECK(branch IN ('transmission','symptomes','capacites')),
            tier        INTEGER NOT NULL DEFAULT 1,
            cost        INTEGER NOT NULL,
            effect_json TEXT    NOT NULL,
            stealth_mod REAL    NOT NULL DEFAULT 0,
            description TEXT
        )
    """)

    # ── Table blueteam ───────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS blueteam (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type       TEXT    NOT NULL,
            trigger_threshold REAL   NOT NULL,
            effect_json      TEXT    NOT NULL,
            description      TEXT
        )
    """)

    # ── Table parties ────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS parties (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL REFERENCES users(id),
            malware_class  TEXT    NOT NULL CHECK(malware_class IN ('worm','trojan','ransomware','rootkit')),
            state_json     TEXT    NOT NULL,
            score          INTEGER DEFAULT 0,
            result         TEXT    CHECK(result IN ('victory','defeat', NULL)),
            started_at     TEXT    DEFAULT (datetime('now')),
            ended_at       TEXT
        )
    """)

    # ── Table config ─────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key         TEXT PRIMARY KEY,
            value       TEXT NOT NULL,
            description TEXT
        )
    """)

    conn.commit()

    # Seed / reseed upgrade data si le nombre d'entrées a changé
    count_up = cur.execute("SELECT COUNT(*) FROM upgrade").fetchone()[0]
    if count_up < 33:  # force reseed si les données ont changé
        cur.execute("DELETE FROM upgrade")
        _seed_upgrades(cur)
        conn.commit()

    # Seed blueteam data if empty
    if cur.execute("SELECT COUNT(*) FROM blueteam").fetchone()[0] == 0:
        _seed_blueteam(cur)
        conn.commit()

    # Seed config data if empty
    if cur.execute("SELECT COUNT(*) FROM config").fetchone()[0] == 0:
        _seed_config(cur)
        conn.commit()

    conn.close()


# ── Seed data ────────────────────────────────────────────────────────

def _seed_upgrades(cur: sqlite3.Cursor):
    # Coûts réduits de ~25% par rapport à l'ancienne version (économie plus tendue avec revenu x0.15)
    # passive_income réduit de ~60% pour rester équilibré face au faible taux de revenu passif
    upgrades = [
        # ════════════════════════════════════════════════════════════
        # WORM — Propagation rapide, bruit élevé
        # ════════════════════════════════════════════════════════════

        # ── Transmission ──
        ("Scan réseau massif", "transmission", 1, 60,
         {"propagation_bonus": 0.08, "allowed_malware": ["worm"]},
         -0.05,
         "Le ver scanne agressivement les sous-réseaux à la recherche d'hôtes vulnérables."),

        ("Exploitation SMB", "transmission", 2, 120,
         {"propagation_bonus": 0.12, "allowed_malware": ["worm"]},
         -0.08,
         "Utilise des failles de partage réseau SMB (type EternalBlue) pour se répliquer latéralement."),

        ("Exploit Zero-Day", "transmission", 3, 225,
         {"propagation_bonus": 0.20, "allowed_malware": ["worm"]},
         -0.12,
         "Exploite une vulnérabilité non patchée pour une propagation sans restriction."),

        # ── Symptômes ──
        ("Cryptomineur distribué", "symptomes", 1, 75,
         {"passive_income": 2, "allowed_malware": ["worm"]},
         -0.10,
         "Détourne le CPU des machines infectées pour miner de la cryptomonnaie."),

        ("Botnet DDoS", "symptomes", 2, 165,
         {"passive_income": 4, "allowed_malware": ["worm"]},
         -0.15,
         "Transforme les machines en réseau de bots pour lancer des attaques DDoS lucratives."),

        ("Exfiltration massive", "symptomes", 3, 260,
         {"income_bonus": 0.15, "allowed_malware": ["worm"]},
         -0.20,
         "Vole et revend les données sensibles de toutes les machines compromises."),

        # ── Capacités ──
        ("Payload polymorphe", "capacites", 1, 90,
         {"stealth": 0.15, "allowed_malware": ["worm"]},
         0.15,
         "Le ver change de signature binaire à chaque réplication, échappant aux antivirus."),

        ("Communication P2P", "capacites", 2, 185,
         {"stealth": 0.10, "propagation_bonus": 0.05, "allowed_malware": ["worm"]},
         0.10,
         "Les instances communiquent en peer-to-peer, rendant le réseau C2 résilient et décentralisé."),

        # ════════════════════════════════════════════════════════════
        # TROJAN — Discret, contourne les défenses
        # ════════════════════════════════════════════════════════════

        # ── Transmission ──
        ("Pièce jointe piégée", "transmission", 1, 75,
         {"propagation_bonus": 0.06, "stealth": 0.08, "allowed_malware": ["trojan"]},
         0.08,
         "Documents Office contenant une macro malveillante signée, difficile à détecter."),

        ("Mouvement latéral RDP", "transmission", 2, 150,
         {"propagation_bonus": 0.10, "allowed_malware": ["trojan"]},
         -0.05,
         "Utilise des identifiants RDP compromis pour pivoter silencieusement entre les machines."),

        ("Watering Hole", "transmission", 3, 240,
         {"propagation_bonus": 0.14, "stealth": 0.05, "allowed_malware": ["trojan"]},
         0.05,
         "Compromet un site web légitime fréquenté par les cibles pour les infecter à leur insu."),

        # ── Symptômes ──
        ("Keylogger furtif", "symptomes", 1, 100,
         {"income_bonus": 0.06, "stealth": 0.05, "allowed_malware": ["trojan"]},
         0.05,
         "Enregistre les frappes clavier en temps réel sans déclencher la moindre alerte."),

        ("Exfiltration DNS", "symptomes", 2, 180,
         {"passive_income": 3, "stealth": 0.10, "allowed_malware": ["trojan"]},
         0.10,
         "Exfiltre les données via des requêtes DNS encodées, quasi indétectable par les pare-feux."),

        ("Vol de credentials", "symptomes", 3, 270,
         {"income_bonus": 0.10, "allowed_malware": ["trojan"]},
         -0.05,
         "Extraction massive des mots de passe stockés dans les navigateurs et gestionnaires."),

        # ── Capacités ──
        ("Certificat SSL volé", "capacites", 1, 110,
         {"stealth": 0.20, "allowed_malware": ["trojan"]},
         0.20,
         "Signe le binaire du trojan avec un certificat numérique légitime volé."),

        ("Backdoor persistante", "capacites", 2, 210,
         {"stealth": 0.15, "propagation_bonus": 0.03, "allowed_malware": ["trojan"]},
         0.15,
         "Installe un accès distant persistant survivant aux redémarrages et mises à jour."),

        # ════════════════════════════════════════════════════════════
        # RANSOMWARE — Revenus massifs, détection rapide
        # ════════════════════════════════════════════════════════════

        # ── Transmission ──
        ("Propagation ver-ransom", "transmission", 1, 100,
         {"propagation_bonus": 0.12, "allowed_malware": ["ransomware"]},
         -0.15,
         "Combine techniques de ver et chiffrement pour se propager et verrouiller rapidement."),

        ("Exploitation EternalBlue", "transmission", 2, 185,
         {"propagation_bonus": 0.18, "allowed_malware": ["ransomware"]},
         -0.20,
         "Utilise la faille NSA EternalBlue pour envahir tout le réseau en quelques ticks."),

        ("Phishing ciblé", "transmission", 3, 260,
         {"propagation_bonus": 0.15, "stealth": 0.05, "allowed_malware": ["ransomware"]},
         0.05,
         "Campagne de spear-phishing ultra ciblée avec des leurres personnalisés."),

        # ── Symptômes ──
        ("Chiffrement partiel", "symptomes", 1, 75,
         {"passive_income": 2, "allowed_malware": ["ransomware"]},
         -0.08,
         "Chiffre partiellement les fichiers pour commencer l'extorsion rapidement."),

        ("Chiffrement AES-256", "symptomes", 2, 165,
         {"income_bonus": 0.12, "allowed_malware": ["ransomware"]},
         -0.15,
         "Chiffrement militaire rendant les données irrécupérables sans la clé."),

        ("Double extorsion", "symptomes", 3, 285,
         {"passive_income": 6, "allowed_malware": ["ransomware"]},
         -0.25,
         "Menace de publier les données volées en plus du chiffrement — pression maximale."),

        # ── Capacités ──
        ("Obfuscation du binaire", "capacites", 1, 120,
         {"stealth": 0.15, "allowed_malware": ["ransomware"]},
         0.15,
         "Techniques de packing et d'obfuscation rendant l'analyse statique difficile."),

        ("Canal C2 via Tor", "capacites", 2, 225,
         {"stealth": 0.25, "allowed_malware": ["ransomware"]},
         0.25,
         "Communications via le réseau Tor pour masquer totalement l'infrastructure de commande."),

        # ════════════════════════════════════════════════════════════
        # ROOTKIT — Quasi-invisible, propagation lente
        # ════════════════════════════════════════════════════════════

        # ── Transmission ──
        ("Dropper furtif", "transmission", 1, 90,
         {"propagation_bonus": 0.05, "stealth": 0.10, "allowed_malware": ["rootkit"]},
         0.10,
         "Charge utile cachée dans des binaires système légitimes."),

        ("Infection bootloader", "transmission", 2, 180,
         {"propagation_bonus": 0.08, "stealth": 0.15, "allowed_malware": ["rootkit"]},
         0.15,
         "S'installe dans le MBR/UEFI, survivant aux reformatages complets du disque."),

        ("Supply chain injection", "transmission", 3, 285,
         {"propagation_bonus": 0.10, "stealth": 0.10, "allowed_malware": ["rootkit"]},
         0.10,
         "Compromet la chaîne d'approvisionnement logicielle pour une infection à la source."),

        # ── Symptômes ──
        ("Keylogger noyau", "symptomes", 1, 105,
         {"income_bonus": 0.04, "stealth": 0.10, "allowed_malware": ["rootkit"]},
         0.10,
         "Intercepte les frappes au niveau kernel, totalement transparent pour l'utilisateur."),

        ("Capture mémoire", "symptomes", 2, 195,
         {"passive_income": 3, "stealth": 0.05, "allowed_malware": ["rootkit"]},
         0.05,
         "Lit la mémoire vive pour extraire mots de passe, clés de chiffrement et tokens."),

        ("Proxy SOCKS caché", "symptomes", 3, 260,
         {"passive_income": 5, "allowed_malware": ["rootkit"]},
         0.00,
         "Transforme la machine en proxy anonyme revendu sur le dark web."),

        # ── Capacités ──
        ("Hooking système", "capacites", 1, 120,
         {"stealth": 0.25, "allowed_malware": ["rootkit"]},
         0.25,
         "Intercepte et modifie les appels système pour cacher toute trace du rootkit."),

        ("Mode fantôme", "capacites", 2, 240,
         {"stealth": 0.35, "allowed_malware": ["rootkit"]},
         0.35,
         "Le rootkit devient quasi invisible à tout outil de détection — furtivité maximale."),
    ]
    for name, branch, tier, cost, effect, stealth, desc in upgrades:
        cur.execute(
            "INSERT INTO upgrade (name, branch, tier, cost, effect_json, stealth_mod, description) VALUES (?,?,?,?,?,?,?)",
            (name, branch, tier, cost, json.dumps(effect), stealth, desc),
        )


def _seed_config(cur: sqlite3.Cursor):
    defaults = [
        ("suspicion_base_factor", "0.12",
         "Facteur de base pour l'augmentation de mefiance par tick"),
        ("tick_interval_seconds", "1.5",
         "Intervalle entre chaque tick de jeu en secondes"),
        ("initial_cpu_cycles", "50",
         "CPU cycles de depart pour une nouvelle partie"),
        ("clean_rate_post_patch", "0.18",
         "Taux de nettoyage par tick apres deploiement du patch"),
        ("bubble_ttl", "6",
         "Duree de vie des bulles cliquables en ticks"),
        ("bubble_spawn_chance", "0.25",
         "Probabilite de spawner une bulle attaquant par tick"),
        ("max_nodes", "30",
         "Nombre de noeuds dans le reseau"),
    ]
    for key, value, desc in defaults:
        cur.execute(
            "INSERT OR IGNORE INTO config (key, value, description) VALUES (?,?,?)",
            (key, value, desc),
        )


def _seed_blueteam(cur: sqlite3.Cursor):
    events = [
        ("scan_heuristique",         30.0, {"detection_rate": 0.10},                     "Scan heuristique déclenché."),
        ("honeypot",                 50.0, {"trap_node": True, "detection_rate": 0.15},   "Honeypot déployé sur le réseau."),
        ("analyse_trafic",           60.0, {"detection_rate": 0.20},                      "Analyse approfondie du trafic réseau."),
        ("patch_securite",          100.0, {"clean_rate": 0.15},                           "Patch de sécurité déployé."),
        ("campagne_sensibilisation", 70.0, {"propagation_penalty": -0.10},                "Campagne de sensibilisation utilisateurs."),
        ("air_gap",                  90.0, {"quarantine": True, "isolation_rate": 0.25},   "Mise en quarantaine Air Gap."),
    ]
    for etype, threshold, effect, desc in events:
        cur.execute(
            "INSERT INTO blueteam (event_type, trigger_threshold, effect_json, description) VALUES (?,?,?,?)",
            (etype, threshold, json.dumps(effect), desc),
        )


# ── CRUD helpers ─────────────────────────────────────────────────────

def create_user(username: str, password_hash: str) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, password_hash),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_user_by_name(username: str) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_user_stats(user_id: int, won: bool, score: int, nodes: int):
    conn = get_connection()
    conn.execute("""
        UPDATE users SET
            games_played = games_played + 1,
            games_won    = games_won + ?,
            best_score   = MAX(best_score, ?),
            total_nodes  = total_nodes + ?
        WHERE id = ?
    """, (1 if won else 0, score, nodes, user_id))
    conn.commit()
    conn.close()


def get_leaderboard(limit: int = 20) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, username, games_played, games_won, best_score, total_nodes FROM users ORDER BY best_score DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_upgrades() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM upgrade ORDER BY branch, tier").fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["effect_json"] = json.loads(d["effect_json"])
        result.append(d)
    return result


def get_blueteam_events() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM blueteam ORDER BY trigger_threshold").fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["effect_json"] = json.loads(d["effect_json"])
        result.append(d)
    return result


def save_party(user_id: int, malware_class: str, state_json: str, score: int = 0) -> int:
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO parties (user_id, malware_class, state_json, score) VALUES (?,?,?,?)",
        (user_id, malware_class, state_json, score),
    )
    conn.commit()
    pid = cur.lastrowid
    conn.close()
    return pid


def update_party(party_id: int, state_json: str, score: int):
    conn = get_connection()
    conn.execute(
        "UPDATE parties SET state_json = ?, score = ? WHERE id = ?",
        (state_json, score, party_id),
    )
    conn.commit()
    conn.close()


def end_party(party_id: int, result: str, score: int):
    conn = get_connection()
    conn.execute(
        "UPDATE parties SET result = ?, score = ?, ended_at = datetime('now') WHERE id = ?",
        (result, score, party_id),
    )
    conn.commit()
    conn.close()


# ── CRUD config ──────────────────────────────────────────────────────

def get_all_config() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM config ORDER BY key").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_config(key: str) -> str | None:
    conn = get_connection()
    row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else None


def set_config(key: str, value: str, description: str = "") -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO config (key, value, description) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value, description),
    )
    conn.commit()
    conn.close()


def delete_config(key: str) -> bool:
    conn = get_connection()
    cur = conn.execute("DELETE FROM config WHERE key = ?", (key,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted
