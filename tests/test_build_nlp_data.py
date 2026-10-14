import gzip
import json
import os
import tempfile
import unittest

from scripts.build_nlp_data import build_french_wordnet


class BuildFrenchWordNetTests(unittest.TestCase):
    def test_builds_normalized_lemma_to_synset_index(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = os.path.join(directory, "source.tab")
            output_path = os.path.join(directory, "wordnet.json.gz")
            with open(source_path, "w", encoding="utf-8") as source:
                source.write("# WOLF test source\n")
                source.write("00000001-n\tfra:lemma\tÉléphant\n")
                source.write("00000001-n\tfra:lemma\tpachyderme\n")
                source.write("00000002-v\tfra:lemma\téléphant\n")
                source.write("00000001-n\tfra:partOfSpeech\tnoun\n")

            build_french_wordnet(source_path, output_path)

            with gzip.open(output_path, "rt", encoding="utf-8") as generated:
                index = json.load(generated)

        self.assertEqual(index, {
            "elephant": ["00000001-n", "00000002-v"],
            "pachyderme": ["00000001-n"],
        })


if __name__ == "__main__":
    unittest.main()
