import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
from tools import (
    finish_study_session,
    get_session_review_items,
    save_session_review_items,
    start_study_session,
)


class SessionReviewItemsTests(unittest.TestCase):
    def test_saves_entire_batch_and_reopening_does_not_duplicate_it(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(database, "DB_PATH", Path(directory) / "test.db"):
                database.initialize_database()
                session = start_study_session("System performance")
                finish_study_session("Latency, throughput, concurrency, and scaling")
                objectives = [
                    "Define latency and interpret P90 and P99.",
                    "Define throughput and its units.",
                    "Explain concurrency.",
                    "Compare horizontal and vertical scaling.",
                    "Explain how bottlenecks limit throughput.",
                ]

                result = save_session_review_items(session["session_id"], objectives)

                self.assertEqual(result["status"], "saved")
                self.assertEqual(
                    [item["learning_objective"] for item in result["items"]],
                    objectives,
                )
                persisted = get_session_review_items(session["session_id"])
                self.assertEqual(persisted, result["items"])
                self.assertEqual(len({item["id"] for item in persisted}), 5)

                reopened = save_session_review_items(session["session_id"], objectives)
                self.assertEqual(reopened["status"], "already_saved")
                self.assertEqual(reopened["items"], persisted)
                self.assertEqual(
                    get_session_review_items(session["session_id"]), persisted
                )


if __name__ == "__main__":
    unittest.main()