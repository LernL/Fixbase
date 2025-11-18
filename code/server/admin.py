#!/usr/bin/env python3
import sqlite3
import secrets
import hashlib
from pathlib import Path
import shlex
import getpass

DB = Path(__file__).resolve().parent / "fixbase.db"

# ---------------- DB helpers ----------------
def connect_db():
    return sqlite3.connect(DB)

def init_db():
    conn = connect_db()
    c = conn.cursor()
    # users
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password_hash TEXT,
        role TEXT,
        token TEXT
    )""")
    # cards
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

    # Створимо default admin/user, якщо їх нема
    def user_exists(username):
        c.execute("SELECT id FROM users WHERE username=?", (username,))
        return c.fetchone() is not None

    if not user_exists("admin"):
        token = secrets.token_hex(16)
        c.execute(
            "INSERT INTO users (username, password_hash, role, token) VALUES (?, ?, ?, ?)",
            ("admin", hashlib.sha256("admin".encode()).hexdigest(), "admin", token)
        )
        print(f"[init] Created admin user. username=admin password=admin token={token}")

    if not user_exists("user"):
        token = secrets.token_hex(16)
        c.execute(
            "INSERT INTO users (username, password_hash, role, token) VALUES (?, ?, ?, ?)",
            ("user", hashlib.sha256("user".encode()).hexdigest(), "user", token)
        )
        print(f"[init] Created user. username=user password=user token={token}")

    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# ---------------- CLI helpers ----------------
def cli_add_user(username, password, role="user"):
    conn = connect_db()
    c = conn.cursor()
    token = secrets.token_hex(16)
    p_hash = hash_password(password)
    try:
        c.execute("INSERT INTO users (username, password_hash, role, token) VALUES (?, ?, ?, ?)",
                  (username, p_hash, role, token))
        conn.commit()
        print(f"User '{username}' created. role={role} token={token}")
    except sqlite3.IntegrityError:
        print(f"User '{username}' already exists. Use force-add-user.")
    finally:
        conn.close()

def cli_force_add_user(username, password, role="user"):
    conn = connect_db()
    c = conn.cursor()
    token = secrets.token_hex(16)
    p_hash = hash_password(password)
    c.execute("INSERT OR REPLACE INTO users (id, username, password_hash, role, token) "
              "VALUES ((SELECT id FROM users WHERE username=?), ?, ?, ?, ?)",
              (username, username, p_hash, role, token))
    conn.commit()
    conn.close()
    print(f"User '{username}' created/updated. role={role} token={token}")

def cli_delete_user(username):
    conn = connect_db()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE username=?", (username,))
    conn.commit()
    conn.close()
    print(f"Deleted user '{username}' (if existed).")

def cli_list_users(show_token=False):
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT id, username, role, token FROM users ORDER BY id")
    rows = c.fetchall()
    conn.close()
    print("Users:")
    for r in rows:
        tok = r[3] if show_token else ("(hidden)" if r[3] else "(none)")
        print(f" id={r[0]} username='{r[1]}' role='{r[2]}' token={tok}")

VALID_ROLES = ["user", "admin", "moderator"]

def cli_set_role(username, role):
    if role not in VALID_ROLES:
        print(f"Invalid role '{role}'. Valid roles: {', '.join(VALID_ROLES)}")
        return
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username=?", (username,))
    if not c.fetchone():
        print(f"User '{username}' does not exist.")
        conn.close()
        return
    c.execute("UPDATE users SET role=? WHERE username=?", (role, username))
    conn.commit()
    conn.close()
    print(f"User '{username}' role updated to '{role}'.")

# ---------------- New: Reset password ----------------
def cli_reset_password(username, new_password=None):
    conn = connect_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username=?", (username,))
    if not c.fetchone():
        print(f"User '{username}' does not exist.")
        conn.close()
        return
    if not new_password:
        new_password = getpass.getpass(f"New password for {username}: ")
    p_hash = hash_password(new_password)
    c.execute("UPDATE users SET password_hash=? WHERE username=?", (p_hash, username))
    conn.commit()
    conn.close()
    print(f"Password for '{username}' updated successfully.")

# ---------------- REPL ----------------
def repl_loop():
    HELP = """
Available commands:
  help
  list-users --show-token
  add-user <username> <password>
  force-add-user <username> <password>
  del-user <username>
  set-role <username> <role>
  reset-password <username> new_password
  exit | quit
"""
    print(HELP)
    while True:
        try:
            line = input("fixbase> ")
        except (EOFError, KeyboardInterrupt):
            print("\nExiting...")
            break
        if not line:
            continue
        parts = shlex.split(line)
        cmd = parts[0].lower()
        args = parts[1:]
        if cmd == "help":
            print(HELP)
        elif cmd == "list-users":
            cli_list_users("--show-token" in args)
        elif cmd == "add-user":
            if len(args) < 2: print("Usage: add-user <username> <password>"); continue
            cli_add_user(args[0], args[1])
        elif cmd == "force-add-user":
            if len(args) < 2: print("Usage: force-add-user <username> <password>"); continue
            cli_force_add_user(args[0], args[1])
        elif cmd in ("del-user", "delete-user"):
            if len(args) != 1: print("Usage: del-user <username>"); continue
            cli_delete_user(args[0])
        elif cmd == "set-role":
            if len(args) != 2: print("Usage: set-role <username> <role>"); continue
            cli_set_role(args[0], args[1])
        elif cmd == "reset-password":
            if len(args) == 0:
                print("Usage: reset-password <username> [new_password]")
                continue
            username = args[0]
            pwd = args[1] if len(args) > 1 else None
            cli_reset_password(username, pwd)
        elif cmd in ("exit", "quit"):
            print("Exiting...")
            break
        else:
            print("Unknown command. Type 'help' for list.")

# ---------------- Main ----------------
if __name__ == "__main__":
    init_db()
    repl_loop()
