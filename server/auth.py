"""
Module d'authentification — hachage bcrypt + vérification.
"""

import bcrypt
from server.database import create_user, get_user_by_name


def register(username: str, password: str) -> dict:
    """Inscrit un nouvel utilisateur. Retourne un dict avec 'ok' ou 'error'."""
    if not username or not password:
        return {"ok": False, "error": "Nom d'utilisateur et mot de passe requis."}
    if len(username) < 3:
        return {"ok": False, "error": "Le nom d'utilisateur doit faire au moins 3 caractères."}
    if len(password) < 4:
        return {"ok": False, "error": "Le mot de passe doit faire au moins 4 caractères."}

    existing = get_user_by_name(username)
    if existing:
        return {"ok": False, "error": "Ce nom d'utilisateur est déjà pris."}

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user_id = create_user(username, hashed)
    return {"ok": True, "user_id": user_id, "username": username}


def login(username: str, password: str) -> dict:
    """Authentifie un utilisateur existant."""
    if not username or not password:
        return {"ok": False, "error": "Nom d'utilisateur et mot de passe requis."}

    user = get_user_by_name(username)
    if not user:
        return {"ok": False, "error": "Identifiants incorrects."}

    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return {"ok": False, "error": "Identifiants incorrects."}

    return {
        "ok": True,
        "user_id": user["id"],
        "username": user["username"],
        "games_played": user["games_played"],
        "games_won": user["games_won"],
        "best_score": user["best_score"],
    }
