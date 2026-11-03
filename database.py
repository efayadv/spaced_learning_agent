import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "teacher.db"

def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection

def initialize_database():
    connection = get_connection()

    try:
        with connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS topics (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE
                );

                CREATE TABLE IF NOT EXISTS review_items (
                    id INTEGER PRIMARY KEY,
                    topic_id INTEGER NOT NULL,
                    learning_objective TEXT NOT NULL,
                    fsrs_card_json TEXT NOT NULL,
                    next_due_at TEXT NOT NULL,
                    FOREIGN KEY (topic_id) REFERENCES topics(id)
                );

                CREATE TABLE IF NOT EXISTS attempts (
                    id INTEGER PRIMARY KEY,
                    review_item_id INTEGER NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    feedback TEXT NOT NULL,
                    fsrs_review_log_json TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL,
                    FOREIGN KEY (review_item_id)
                        REFERENCES review_items(id)
                );

                CREATE INDEX IF NOT EXISTS idx_review_items_due
                ON review_items(next_due_at);

                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY,
                    topic_id INTEGER NOT NULL REFERENCES topics(id),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    legacy_session_id INTEGER UNIQUE,
                    UNIQUE (topic_id, content)
                );

                CREATE TABLE IF NOT EXISTS note_review_items (
                    note_id INTEGER NOT NULL REFERENCES notes(id),
                    review_item_id INTEGER NOT NULL REFERENCES review_items(id),
                    PRIMARY KEY (note_id, review_item_id)
                );

                CREATE TABLE IF NOT EXISTS reminder_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    enabled INTEGER NOT NULL DEFAULT 0,
                    daily_time TEXT NOT NULL DEFAULT '12:00',
                    followup_enabled INTEGER NOT NULL DEFAULT 1,
                    followup_time TEXT NOT NULL DEFAULT '19:00',
                    timezone TEXT NOT NULL DEFAULT 'America/Chicago'
                );

                INSERT OR IGNORE INTO reminder_settings (id) VALUES (1);

                CREATE TABLE IF NOT EXISTS reminder_deliveries (
                    local_date TEXT NOT NULL,
                    slot TEXT NOT NULL,
                    sent_at TEXT NOT NULL,
                    PRIMARY KEY (local_date, slot)
                );
            """)
            # Copy old notes and their review links without deleting historical data.
            legacy = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'study_sessions'"
            ).fetchone()
            if legacy:
                connection.execute("""
                    INSERT OR IGNORE INTO notes (topic_id, content, created_at, legacy_session_id)
                    SELECT topic_id, TRIM(notes), COALESCE(ended_at, started_at), id
                    FROM study_sessions WHERE notes IS NOT NULL AND TRIM(notes) != ''
                """)
                links = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'session_review_items'"
                ).fetchone()
                if links:
                    connection.execute("""
                        INSERT OR IGNORE INTO note_review_items (note_id, review_item_id)
                        SELECT n.id, link.review_item_id FROM session_review_items AS link
                        JOIN study_sessions AS s ON s.id = link.session_id
                        JOIN notes AS n ON n.topic_id = s.topic_id AND n.content = TRIM(s.notes)
                    """)
    finally:
        connection.close()