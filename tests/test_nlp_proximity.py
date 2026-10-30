import unittest

from app.nlp import (
    FRENCH_VERB_LEMMAS,
    WORD_ASSOCIATIONS,
    calculate_proximity,
    calculate_numeric_proximity,
    calculate_word2vec_cosine,
    calculate_word2vec_proximity,
    get_verb_stems,
    is_valid_french_word,
    normalize_text,
    REGULAR_VERB_SUFFIXES,
)
from app.synonyms_dict import CURATED_DOMAIN_ASSOCIATIONS


class ProximityTests(unittest.TestCase):
    def test_verb_suffix_index_preserves_all_previous_stems(self):
        for word in (
            "chevaux", "courent", "mangeais", "finissons", "parlèrent",
            "exercices", "univers", "généralement", "1985", "avait",
        ):
            expected = {
                word[:-len(suffix)]
                for suffix in REGULAR_VERB_SUFFIXES
                if word.endswith(suffix) and len(word[:-len(suffix)]) >= 2
            }
            with self.subTest(word=word):
                self.assertEqual(set(get_verb_stems(word)), expected)

    def test_numeric_proximity_thresholds_scale_with_target_magnitude(self):
        for guess, target, expected, beyond in (
            (30_000, 10_000, 20_000, 20_001),
            (3_500, 2_500, 1_000, 1_001),
            (600, 500, 100, 101),
        ):
            with self.subTest(target=target):
                self.assertEqual(
                    calculate_numeric_proximity(guess, target),
                    48.0,
                )
                self.assertEqual(
                    calculate_numeric_proximity(target + beyond, target),
                    0.0,
                )
                self.assertGreater(
                    calculate_proximity(str(target + expected // 2), str(target)),
                    48.0,
                )

    def test_pedantix_proximity_uses_word2vec_and_keeps_exact_morphology(self):
        self.assertGreater(
            calculate_word2vec_proximity("chien", "chat"),
            calculate_word2vec_proximity("voiture", "chat"),
        )
        self.assertEqual(calculate_word2vec_proximity("chat", "chats"), 100.0)
        self.assertEqual(calculate_word2vec_proximity("motinconnuabc", "chat"), 0.0)

    def test_word2vec_similarity_keeps_contextual_antonyms_close(self):
        self.assertGreater(
            calculate_word2vec_cosine("chaud", "froid"),
            calculate_word2vec_cosine("voiture", "chat"),
        )

    def test_embeddings_add_related_word_coverage(self):
        self.assertGreaterEqual(calculate_proximity("ordinateur", "écran"), 75.0)
        self.assertGreaterEqual(calculate_proximity("avion", "atterrir"), 85.0)
        self.assertGreaterEqual(calculate_proximity("cuisine", "recette"), 70.0)

    def test_dictionary_synonyms_keep_their_high_confidence_score(self):
        self.assertGreaterEqual(calculate_proximity("voiture", "automobile"), 90.0)

    def test_wordnet_synsets_add_sense_based_synonyms(self):
        self.assertGreaterEqual(calculate_proximity("inspirer", "respirer"), 90.0)

    def test_wiktionary_synsets_add_complementary_synonyms(self):
        self.assertGreaterEqual(calculate_proximity("aberrant", "délirant"), 90.0)

    def test_curated_verb_associations_apply_to_infinitives_and_conjugations(self):
        for verb_form, related_word, minimum_score in (
            ("aboyer", "chien", 84.0),
            ("aboyait", "chien", 84.0),
            ("nageait", "piscine", 84.0),
            ("décoller", "avion", 84.0),
            ("défendait", "tribunal", 78.0),
            ("élisait", "élection", 84.0),
            ("recevait", "courrier", 84.0),
            ("résous", "problème", 84.0),
            ("détruisait", "bâtiment", 80.0),
            ("réduisait", "quantité", 78.0),
            ("éteignait", "lumière", 84.0),
        ):
            with self.subTest(verb_form=verb_form, related_word=related_word):
                self.assertGreaterEqual(
                    calculate_proximity(verb_form, related_word),
                    minimum_score,
                )

    def test_wordnet_expands_the_valid_french_vocabulary(self):
        self.assertTrue(is_valid_french_word("abeillaud"))

    def test_added_irregular_verb_forms_resolve_to_their_lemmas(self):
        for form, lemma in (
            ("reçoivent", "recevoir"),
            ("reçurent", "recevoir"),
            ("résolvaient", "résoudre"),
            ("résoudront", "résoudre"),
            ("détruisirent", "détruire"),
            ("détruites", "détruire"),
            ("réduirons", "réduire"),
            ("réduites", "réduire"),
            ("éteignons", "éteindre"),
            ("éteintes", "éteindre"),
        ):
            with self.subTest(form=form):
                self.assertEqual(
                    FRENCH_VERB_LEMMAS[normalize_text(form)],
                    normalize_text(lemma),
                )

    def test_curated_domain_associations_cover_new_word_families(self):
        for first, second, minimum_score in (
            ("cœur", "artère", 82.0),
            ("cerveau", "neurone", 88.0),
            ("poumon", "bronche", 86.0),
            ("fleuve", "delta", 84.0),
            ("volcan", "magma", 86.0),
            ("internet", "navigateur", 84.0),
            ("robot", "capteur", 82.0),
            ("atome", "électron", 88.0),
            ("recette", "ingrédient", 88.0),
            ("train", "locomotive", 82.0),
            ("poésie", "strophe", 84.0),
            ("grammaire", "syntaxe", 88.0),
        ):
            with self.subTest(first=first, second=second):
                self.assertGreaterEqual(
                    calculate_proximity(first, second),
                    minimum_score,
                )

    def test_curated_domain_words_are_available_and_scores_are_valid(self):
        for word, associations in CURATED_DOMAIN_ASSOCIATIONS.items():
            normalized_word = normalize_text(word)
            with self.subTest(word=word):
                self.assertTrue(is_valid_french_word(word))
                self.assertTrue(WORD_ASSOCIATIONS[normalized_word])
                self.assertTrue(
                    all(0 < score <= 100 for score in associations.values())
                )

    def test_distributional_similarity_does_not_claim_synonym_confidence(self):
        score = calculate_proximity("chaud", "froid")
        self.assertGreaterEqual(score, 48.0)
        self.assertLess(score, 90.0)

    def test_shared_etymology_does_not_claim_semantic_proximity(self):
        for first, second in (
            ("père", "patrie"),
            ("roi", "régime"),
            ("livre", "lettre"),
            ("biographie", "biologie"),
            ("montagne", "montant"),
        ):
            with self.subTest(first=first, second=second):
                self.assertLess(calculate_proximity(first, second), 88.0)

    def test_related_but_non_synonymous_words_keep_moderate_scores(self):
        self.assertLess(calculate_proximity("montagne", "vallée"), 90.0)
        self.assertEqual(calculate_proximity("mont", "crème"), 0.0)

    def test_known_false_friends_remain_unrelated(self):
        for first, second in (
            ("enfant", "enfer"),
            ("talent", "talons"),
            ("parent", "parer"),
            ("lit", "lire"),
            ("souris", "sourire"),
            ("bois", "boire"),
            ("cours", "courir"),
            ("vers", "verser"),
            ("fond", "fondre"),
            ("sens", "sentir"),
            ("tour", "tourner"),
            ("pas", "passer"),
            ("plat", "plaire"),
            ("vent", "vendre"),
            ("pain", "peine"),
            ("chat", "chambre"),
            ("sang", "sangle"),
            ("cote", "coton"),
            ("point", "pointer"),
            ("banc", "banque"),
            ("mer", "mère"),
            ("port", "porte"),
        ):
            with self.subTest(first=first, second=second):
                self.assertEqual(calculate_proximity(first, second), 0.0)

    def test_unknown_words_without_embeddings_remain_unrelated(self):
        self.assertEqual(calculate_proximity("motinconnuabc", "motinconnuxyz"), 0.0)


if __name__ == "__main__":
    unittest.main()
