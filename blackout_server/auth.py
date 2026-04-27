import bcrypt
from server.database import create_user as db_create_user, get_user_by_name

def register(username, password):
    if get_user_by_name(username): return {"ok": False, "error": "Utilisateur existe déjà."}
    pwd_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    uid = db_create_user(username, pwd_hash)
    return {"ok": True, "user_id": uid, "username": username}

def login(username, password):
    user = get_user_by_name(username)
    if not user: return {"ok": False, "error": "Utilisateur non trouvé."}
    if bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
        return {"ok": True, "user_id": user['id'], "username": user['username']}
    return {"ok": False, "error": "Mot de passe incorrect."}
