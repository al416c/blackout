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

    conn.commit()

    # Seed / reseed upgrade data if peu d'entrées
    count_up = cur.execute("SELECT COUNT(*) FROM upgrade").fetchone()[0]
    if count_up < 10:
        cur.execute("DELETE FROM upgrade")
        _seed_upgrades(cur)
        conn.commit()

    # Seed blueteam data if empty
    if cur.execute("SELECT COUNT(*) FROM blueteam").fetchone()[0] == 0:
        _seed_blueteam(cur)
        conn.commit()

    conn.close()


# ── Seed data ────────────────────────────────────────────────────────

def _seed_upgrades(cur: sqlite3.Cursor):
    upgrades = [
        # ── Transmission (propagation) ────────────────────────────
        # Worm
        ("Scan réseau massif", "transmission", 1, 80,
         {"propagation_bonus": 0.10, "allowed_malware": ["worm"]},
         -0.05,
         "Optimisation du ver pour scanner rapidement de nouveaux hôtes."),

        ("Injection SMB", "transmission", 2, 200,
         {"propagation_bonus": 0.20, "allowed_malware": ["worm"]},
         -0.10,
         "Exploitation de partages SMB pour se répliquer latéralement."),

        # Trojan
        ("Cheval de Troie bureautique", "transmission", 1, 100,
         {"propagation_bonus": 0.08, "stealth": 0.10, "allowed_malware": ["trojan"]},
         0.10,
         "Pièces jointes bureautiques signées, difficiles à détecter."),

        ("Mouvement latéral RDP", "transmission", 2, 220,
         {"propagation_bonus": 0.12, "allowed_malware": ["trojan"]},
         -0.05,
         "Exploitation d'identifiants RDP compromis pour pivoter."),

        # Ransomware
        ("Propagation ver-ransom", "transmission", 1, 130,
         {"propagation_bonus": 0.15, "allowed_malware": ["ransomware"]},
         -0.15,
         "Combinaison de techniques de ver et de ransomware."),

        # Rootkit
        ("Dropper furtif", "transmission", 1, 120,
         {"propagation_bonus": 0.06, "stealth": 0.15, "allowed_malware": ["rootkit"]},
         0.15,
         "Charge utile cachée dans des binaires légitimes."),

        # ── Symptômes (monétisation / dégâts) ─────────────────────
        ("Keylogger furtif", "symptomes", 1, 140,
         {"income_bonus": 0.05, "data_capture": True, "allowed_malware": ["trojan", "rootkit"]},
         0.05,
         "Enregistre les frappes clavier en limitant le bruit généré."),

        ("Cryptomineur distribué", "symptomes", 2, 260,
         {"passive_income": 8, "allowed_malware": ["worm", "ransomware"]},
         -0.20,
         "Détourne les ressources CPU des machines infectées."),

        ("Chiffrement agressif", "symptomes", 3, 380,
         {"damage": 0.40, "noise": 0.30, "allowed_malware": ["ransomware"]},
         -0.30,
         "Chiffre massivement les données, accélérant la détection."),

        # ── Capacités (furtivité / défense) ───────────────────────
        ("Chiffrement du code", "capacites", 1, 180,
         {"stealth": 0.20, "allowed_malware": ["worm", "trojan", "ransomware", "rootkit"]},
         0.20,
         "Obfuscation et chiffrement rendant le binaire plus difficile à analyser."),

        ("Désactivation avancée des logs", "capacites", 2, 320,
         {"stealth": 0.35, "disable_logs": True, "allowed_malware": ["rootkit", "trojan"]},
         0.35,
         "Altère la journalisation système pour masquer les traces."),

        ("Canal C2 chiffré", "capacites", 3, 260,
         {"stealth": 0.15, "income_bonus": 0.05, "allowed_malware": ["ransomware", "trojan"]},
         0.10,
         "Canal de commande et contrôle chiffré pour exfiltrer en douceur."),
    ]
    for name, branch, tier, cost, effect, stealth, desc in upgrades:
        cur.execute(
            "INSERT INTO upgrade (name, branch, tier, cost, effect_json, stealth_mod, description) VALUES (?,?,?,?,?,?,?)",
            (name, branch, tier, cost, json.dumps(effect), stealth, desc),
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
