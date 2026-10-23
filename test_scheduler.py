from datetime import datetime, timezone
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import database
from fsrs import Card, Rating
from scheduler import fit_review_window, schedule_next_review
from tools import add_review_item, align_existing_review_times


class ReviewWindowTests(unittest.TestCase):
    def test_window_boundaries_and_daylight_saving(self):
        cases = [
            ('2026-10-23T00:53:04+00:00', '2026-10-23T00:53:04+00:00'),
            ('2026-10-23T15:00:00+00:00', '2026-10-23T17:00:00+00:00'),
            ('2026-10-24T03:00:00+00:00', '2026-10-24T03:00:00+00:00'),
            ('2026-10-24T03:00:01+00:00', '2026-10-24T17:00:00+00:00'),
            ('2026-11-01T04:00:00+00:00', '2026-11-01T18:00:00+00:00'),
            ('2027-03-14T05:00:00+00:00', '2027-03-14T17:00:00+00:00'),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(fit_review_window(datetime.fromisoformat(source)), datetime.fromisoformat(expected))

    def test_fsrs_output_is_adjusted(self):
        card = Card()
        card.due = datetime(2026, 10, 23, 10, tzinfo=timezone.utc)
        with patch('scheduler.scheduler.review_card', return_value=(card, 'log')):
            updated, log = schedule_next_review(Card(), Rating.Good)
        self.assertEqual(updated.due, datetime(2026, 10, 23, 17, tzinfo=timezone.utc))
        self.assertEqual(log, 'log')

    def test_existing_card_and_database_stay_in_sync(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(database, 'DB_PATH', Path(directory) / 'test.db'):
                database.initialize_database()
                item_id = add_review_item('Testing', 'Explain a concept')
                card = Card()
                card.due = datetime(2026, 10, 23, 10, tzinfo=timezone.utc)
                c = database.get_connection()
                try:
                    with c:
                        c.execute('UPDATE review_items SET next_due_at = ?, fsrs_card_json = ? WHERE id = ?', (card.due.isoformat(), card.to_json(), item_id))
                    self.assertEqual(align_existing_review_times(), 1)
                    row = c.execute('SELECT next_due_at, fsrs_card_json FROM review_items WHERE id = ?', (item_id,)).fetchone()
                    expected = datetime(2026, 10, 23, 17, tzinfo=timezone.utc)
                    self.assertEqual(datetime.fromisoformat(row['next_due_at']), expected)
                    self.assertEqual(Card.from_json(row['fsrs_card_json']).due, expected)
                    self.assertEqual(align_existing_review_times(), 0)
                finally:
                    c.close()


if __name__ == '__main__':
    unittest.main()
