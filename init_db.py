import os
import psycopg2

def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])

def create_tables():
    conn = get_conn()
    cur = conn.cursor()

    # USERS table (sign ups)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        email TEXT,
        name TEXT,
        password TEXT,
        company TEXT,
        phone TEXT,
        abn TEXT,
        address TEXT,
        logo_filename TEXT,
        submitted_at TEXT
    );
    """)

    # SUBMISSIONS table (calculator results)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS submissions (
        id TEXT PRIMARY KEY,
        email TEXT,
        inputs TEXT,
        result TEXT,
        assumptions TEXT,
        rates TEXT,
        submitted_at TEXT
    );
    """)

    conn.commit()
    cur.close()
    conn.close()

    print("DONE — DATABASE READY ✅")

if __name__ == "__main__":
    create_tables()