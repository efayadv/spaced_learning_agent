import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import database
from agent import execute_tool
from tools import add_review_item, find_notes, save_notes


class NotesTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        patcher = patch.object(database, "DB_PATH", Path(self.directory.name) / "test.db")
        patcher.start()
        self.addCleanup(patcher.stop)
        database.initialize_database()
        self.arguments = {
            "topic": "Performance",
            "notes": "Latency measures delay. Throughput measures work per unit time.",
            "objectives": ["Explain latency.", "Explain throughput."],
        }

    def test_notes_and_objectives_persist_without_a_session_and_do_not_duplicate(self):
        result = save_notes(**self.arguments)
        self.assertEqual(result["status"], "saved")
        self.assertEqual(len(result["items"]), 2)
        notes = find_notes("latency")
        self.assertEqual(notes[0]["notes"], self.arguments["notes"])
        self.assertEqual(notes[0]["note_id"], result["note_id"])
        repeated = save_notes(**self.arguments)
        self.assertEqual(repeated["status"], "already_saved")
        self.assertEqual(repeated["items"], result["items"])
        other = save_notes("Performance", "Concurrency is overlapping work.", ["Explain concurrency."])
        self.assertNotEqual(other["note_id"], result["note_id"])

    def test_invalid_batch_does_not_save_notes(self):
        for change in ({"notes": " "}, {"topic": ""}, {"objectives": []},
                       {"objectives": ["Explain latency.", "explain latency."]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                save_notes(**(self.arguments | change))
        self.assertEqual(find_notes("Performance"), [])

    def test_tool_approval_and_review_mode(self):
        call = SimpleNamespace(name="save_notes", arguments=json.dumps(self.arguments))
        allowed = set()
        with patch("builtins.input", return_value="n"):
            result = execute_tool(call, True, allowed, {})
        self.assertEqual(result["status"], "declined")
        self.assertEqual(find_notes("Performance"), [])
        self.assertEqual(execute_tool(call, False, allowed, {})["status"], "error")
        with patch("builtins.input", return_value="y"):
            result = execute_tool(call, True, allowed, {})
        self.assertEqual(result["status"], "saved")
        self.assertEqual(allowed, {item["id"] for item in result["items"]})

    def test_legacy_notes_migrate_on_repeated_initialization(self):
        connection = database.get_connection()
        try:
            with connection:
                connection.executescript("""
                    INSERT INTO topics (id, name) VALUES (1, 'Legacy');
                    CREATE TABLE study_sessions (
                        id INTEGER PRIMARY KEY, topic_id INTEGER, started_at TEXT,
                        ended_at TEXT, notes TEXT
                    );
                    INSERT INTO study_sessions VALUES
                        (1, 1, '2026-01-01', '2026-01-02', 'Old notes');
                    CREATE TABLE session_review_items (session_id INTEGER, review_item_id INTEGER);
                """)
            item_id = add_review_item("Legacy", "Explain the old notes.")
            with connection:
                connection.execute("INSERT INTO session_review_items VALUES (1, ?)", (item_id,))
            database.initialize_database()
            database.initialize_database()
            links = connection.execute("SELECT review_item_id FROM note_review_items").fetchall()
            self.assertEqual([row["review_item_id"] for row in links], [item_id])
            self.assertEqual(len(find_notes("Legacy")), 1)
            self.assertEqual(find_notes("Legacy")[0]["notes"], "Old notes")
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
