import os
import psycopg2

def get_db_connection():
    return psycopg2.connect(
        os.environ["DATABASE_URL"].replace("postgres://", "postgresql://")
    )

def create_tables():
    conn = get_db_connection()
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

    # ASSUMPTIONS table (FIXED)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS assumptions (
        id TEXT PRIMARY KEY,
        email TEXT,
        data TEXT,
        created_at TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS submissions (
        id TEXT PRIMARY KEY,
        email TEXT,
        inputs TEXT,
        result TEXT,
        assumptions TEXT,
        rates JSONB,
        submitted_at TEXT
    );
    
    """)

    cur.execute("""
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name='submissions'
            AND column_name='rates'
            AND data_type!='jsonb'
        ) THEN
            ALTER TABLE submissions
            ALTER COLUMN rates TYPE JSONB
            USING rates::jsonb;
        END IF;
    END $$;
    """)

# extra safety (can be removed since column already exists above)
    cur.execute("""
    ALTER TABLE submissions
    ALTER COLUMN rates TYPE JSONB
    USING rates::jsonb;
    """)

    # PASSWORD RESET TOKENS
    cur.execute("""
    CREATE TABLE IF NOT EXISTS password_resets (
        id TEXT PRIMARY KEY,
        email TEXT,
        token TEXT,
        expires_at TEXT
    );
    """)

    conn.commit()
    cur.close()
    conn.close()

    print("DONE — DATABASE READY ✅")

if __name__ == "__main__":
    create_tables()