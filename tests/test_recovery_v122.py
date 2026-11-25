import unittest
from scripts.modeling.recovery_v122 import digest, normalized, valid_url, validate_source


class RecoveryAuditTests(unittest.TestCase):
    def test_hash_and_normalization(self):
        self.assertEqual(digest(b"abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        self.assertEqual(normalized("Prévoyance   vieillesse"), "prevoyance vieillesse")

    def test_only_official_hosts(self):
        self.assertTrue(valid_url("https://www.bk.admin.ch/a.pdf"))
        self.assertFalse(valid_url("https://www.bk.admin.ch.example.org/a.pdf"))
        self.assertFalse(valid_url("http://www.admin.ch/a.pdf"))

    def test_nonprior_evidence_rejected(self):
        with self.assertRaises(ValueError):
            validate_source({"vote_date": "2022-05-15", "catalog_publication": "2022-05-15"})

    def test_holdout_rejected(self):
        with self.assertRaises(ValueError):
            validate_source({"vote_date": "2023-06-18"})
