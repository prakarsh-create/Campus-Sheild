import json
import unittest
from datetime import datetime
from types import SimpleNamespace

from app.matching import find_matches


class FakeResult:
    def __init__(self, items):
        self.items = items

    def all(self):
        return self.items


class FakeSession:
    def __init__(self, candidates):
        self.candidates = candidates
        self.commits = 0

    def scalars(self, _statement):
        return FakeResult(self.candidates)

    def commit(self):
        self.commits += 1


def make_item(item_id, item_type, title, embedding=None):
    return SimpleNamespace(
        id=item_id,
        type=item_type,
        title=title,
        category="gadgets",
        description="",
        location="Library",
        event_time=datetime(2026, 1, 1, 12),
        created_at=datetime(2026, 1, 1, 12),
        reporter_id=item_id,
        status="open",
        image_path=None,
        image_embedding=json.dumps(embedding) if embedding is not None else None,
    )


class FindMatchesTests(unittest.TestCase):
    def test_similar_images_can_match_without_text_overlap(self):
        item = make_item(1, "lost", "blue object", [1.0, 0.0])
        candidate = make_item(2, "found", "red object", [0.9, 0.43589])

        matches = find_matches(FakeSession([candidate]), item)

        self.assertEqual(len(matches), 1)
        self.assertIn("Visually similar image", matches[0][2])
        self.assertGreaterEqual(matches[0][1], 80)
        self.assertEqual(matches[0][3], 90)

    def test_items_without_images_keep_metadata_match_behavior(self):
        item = make_item(1, "lost", "black calculator")
        candidate = make_item(2, "found", "black calculator")

        matches = find_matches(FakeSession([candidate]), item)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][1], 100)
        self.assertIsNone(matches[0][3])

    def test_unrelated_text_without_images_does_not_match(self):
        item = make_item(1, "lost", "black calculator")
        candidate = make_item(2, "found", "silver bottle")

        self.assertEqual(find_matches(FakeSession([candidate]), item), [])


if __name__ == "__main__":
    unittest.main()
