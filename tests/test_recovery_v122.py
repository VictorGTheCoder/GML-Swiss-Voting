import unittest
from unittest.mock import patch

from scripts.modeling.recovery_v122 import (
    audit,
    digest,
    normalized,
    source_urls,
    valid_url,
    validate_source,
)


class RecoveryAuditTests(unittest.TestCase):
    def test_hash_and_normalization(self):
        self.assertEqual(digest(b"abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        self.assertEqual(normalized("Prévoyance   vieillesse"), "prevoyance vieillesse")

    def test_only_official_hosts(self):
        self.assertTrue(valid_url("https://www.bk.admin.ch/a.pdf"))
        self.assertFalse(valid_url("https://www.bk.admin.ch.example.org/a.pdf"))
        self.assertFalse(valid_url("http://www.admin.ch/a.pdf"))
        self.assertTrue(valid_url("https://www.fr.ch/a.pdf"))
        self.assertFalse(valid_url("https://www.fr.ch.evil.example/a.pdf"))
        self.assertFalse(valid_url("https://www.fr.ch:8443/a.pdf"))

    def test_nonprior_evidence_rejected(self):
        with self.assertRaises(ValueError):
            validate_source({"vote_date": "2022-05-15", "catalog_publication": "2022-05-15"})

    def test_holdout_rejected(self):
        with self.assertRaises(ValueError):
            validate_source({"vote_date": "2023-06-18"})

    def test_distinct_mirror_list(self):
        self.assertEqual(source_urls({"url": "a", "alternate_url": "b",
                                      "additional_urls": ["a", "c"]}), ["a", "b", "c"])

    def test_mirrors_compared_by_date_without_admission(self):
        source = {"vote_date": "2017-09-24", "url": "a", "additional_urls": ["b", "c"],
                  "objects": [{"vote_id": "6130"}]}
        with patch("scripts.modeling.recovery_v122.download", side_effect=[b"a", OSError("offline"), b"c"]), patch(
            "scripts.modeling.recovery_v122.inspect_pdf", side_effect=[{"pdf_sha256": "1"}, {"pdf_sha256": "2"}]
        ):
            result = audit({"sources": [source]})
        self.assertEqual(result["by_date"]["2017-09-24"],
                         {"hashed_mirrors": 2, "mirror_bytes_equal": False})
        self.assertEqual(result["training_rows"], 0)
        self.assertFalse(result["strict_forecast_ready"])
