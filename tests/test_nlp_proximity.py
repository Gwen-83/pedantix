import unittest

from app.nlp import calculate_proximity, normalize_text


class ProximityTests(unittest.TestCase):
    def test_exact_matches_score_one_hundred(self):
        self.assertEqual(calculate_proximity("chat", "chat"), 100.0)

    def test_guess_cleanup_preserves_exact_word_matches(self):
        self.assertEqual(calculate_proximity("chat!", "chat"), 100.0)

    def test_curated_synonyms_keep_their_high_confidence_score(self):
        self.assertEqual(calculate_proximity("voiture", "automobile"), 96.5)

    def test_related_words_use_the_legacy_curated_associations(self):
        self.assertEqual(calculate_proximity("pomme", "fruit"), 90.0)

    def test_years_use_the_legacy_numeric_proximity(self):
        self.assertEqual(calculate_proximity("1900", "1901"), 99.0)
        self.assertEqual(calculate_proximity("1900", "2100"), 0.0)

    def test_empty_and_unrelated_words_score_zero(self):
        self.assertEqual(calculate_proximity("", "chat"), 0.0)
        self.assertEqual(calculate_proximity("qzxw", "plmko"), 0.0)

    def test_normalization_remains_available(self):
        self.assertEqual(normalize_text("Éléphant"), "elephant")


if __name__ == "__main__":
    unittest.main()
