import sqlite3
import hashlib

DB = "backend/storage/monitor.db"

def login(username,password):

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    hashed = hashlib.sha256(password.encode()).hexdigest()

    cur.execute(
        "SELECT * FROM users WHERE username=? AND password=?",
        (username,hashed)
    )

    user = cur.fetchone()

    conn.close()

    return user