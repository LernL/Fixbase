import json
import secrets
import hashlib
import sqlite3
from pathlib import Path
from functools import wraps
from flask import Flask, request, jsonify

# --- Configuration ---
DB = Path(__file__).resolve().parent / "fixbase.db"
app = Flask(__name__)


# --- DB Helpers ---
def connect_db():
    """Підключення до SQLite."""
    return sqlite3.connect(DB)


def row_to_user(r):
    return {"id": r[0], "username": r[1], "role": r[2], "token": r[3]}


def row_to_card(r):
    return {
        "id": r[0],
        "title": r[1],
        "description": r[2],
        "steps": r[3],
        "cli_commands": json.loads(r[4] or "[]"),
        "tags": json.loads(r[5] or "[]"),
        "created_at": r[6],
        "verified": bool(r[7]),
        "history": json.loads(r[8] or "[]"),
    }


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def init_db():
    """Ініціалізація таблиць та дефолтних користувачів"""
    conn = connect_db()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password_hash TEXT,
        role TEXT,
        token TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        description TEXT,
        steps TEXT,
        cli_commands TEXT,
        tags TEXT,
        created_at TEXT,
        verified INTEGER,
        history TEXT
    )""")

    def user_exists(username):
        c.execute("SELECT id FROM users WHERE username=?", (username,))
        return c.fetchone() is not None

    if not user_exists("admin"):
        token = secrets.token_hex(16)
        c.execute(
            "INSERT INTO users (username, password_hash, role, token) VALUES (?, ?, ?, ?)",
            ("admin", hash_password("admin"), "admin", token)
        )
        print(f"[init] Created admin. Token={token}")

    if not user_exists("user"):
        token = secrets.token_hex(16)
        c.execute(
            "INSERT INTO users (username, password_hash, role, token) VALUES (?, ?, ?, ?)",
            ("user", hash_password("user"), "user", token)
        )
        print(f"[init] Created user. Token={token}")

    conn.commit()
    conn.close()


def get_user_by_token(token):
    if not token: return None
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT id, username, role FROM users WHERE token=?", (token,))
    row = c.fetchone()
    conn.close()
    return {"id": row[0], "username": row[1], "role": row[2]} if row else None


# --- Middleware ---
def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        token = auth.split(" ", 1)[1].strip() if auth.startswith("Bearer ") else None
        user = get_user_by_token(token)
        if not user or user.get("role") != "admin":
            return jsonify({"error": "admin required"}), 401
        return fn(*args, **kwargs)

    return wrapper


# --- Routes ---
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    username = data.get("username", "")
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"error": "username+password required"}), 400

    p_hash = hash_password(password)
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT id, role, token FROM users WHERE username=? AND password_hash=?", (username, p_hash))
    row = c.fetchone()

    if row:
        uid, role, token = row
        if not token:
            token = secrets.token_hex(16)
            c.execute("UPDATE users SET token=? WHERE id=?", (token, uid))
            conn.commit()
        conn.close()
        return jsonify({"token": token, "role": role, "username": username})

    conn.close()
    return jsonify({"error": "invalid credentials"}), 401


@app.route("/users", methods=["GET"])
@require_admin
def get_users():
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT id, username, role, token FROM users ORDER BY id")
    rows = c.fetchall()
    conn.close()
    return jsonify([row_to_user(r) for r in rows])


@app.route("/cards", methods=["GET"])
def get_cards():
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT * FROM cards ORDER BY id")
    rows = c.fetchall()
    conn.close()
    return jsonify([row_to_card(r) for r in rows])


@app.route("/cards", methods=["POST"])
@require_admin
def add_card():
    data = request.get_json(force=True)
    title = data.get("title", "")

    if not title:
        return jsonify({"error": "title required"}), 400

    conn = connect_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO cards (title, description, steps, cli_commands, tags, created_at, verified, history) "
        "VALUES (?, ?, ?, ?, ?, datetime('now'), 0, ?)",
        (
            title,
            data.get("description", ""),
            data.get("steps", ""),
            json.dumps(data.get("cli_commands", [])),
            json.dumps(data.get("tags", [])),
            json.dumps([])
        )
    )
    conn.commit()
    card_id = c.lastrowid
    c.execute("SELECT * FROM cards WHERE id=?", (card_id,))
    row = c.fetchone()
    conn.close()
    return jsonify(row_to_card(row)), 201


@app.route("/cards/<int:card_id>/verify", methods=["POST"])
@require_admin
def verify_card(card_id):
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT id FROM cards WHERE id=?", (card_id,))
    if not c.fetchone():
        conn.close()
        return jsonify({"error": "card not found"}), 404

    c.execute("UPDATE cards SET verified=1 WHERE id=?", (card_id,))
    conn.commit()
    c.execute("SELECT * FROM cards WHERE id=?", (card_id,))
    updated_row = c.fetchone()
    conn.close()
    return jsonify(row_to_card(updated_row)), 200


@app.route("/cards/<int:card_id>", methods=["DELETE"])
@require_admin
def delete_card(card_id):
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT id FROM cards WHERE id=?", (card_id,))
    if not c.fetchone():
        conn.close()
        return jsonify({"error": "card not found"}), 404

    c.execute("DELETE FROM cards WHERE id=?", (card_id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "deleted"}), 200

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "username+password required"}), 400

    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username=?", (username,))
    if c.fetchone():
        conn.close()
        return jsonify({"error": "username already exists"}), 409

    token = secrets.token_hex(16)
    p_hash = hash_password(password)
    c.execute(
        "INSERT INTO users (username, password_hash, role, token) VALUES (?, ?, ?, ?)",
        (username, p_hash, "user", token)
    )
    conn.commit()
    conn.close()

    return jsonify({"token": token, "role": "user", "username": username}), 201


if __name__ == "__main__":
    init_db()
    print(f"DB file: {DB.resolve()}")
    print("Starting server on http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000)