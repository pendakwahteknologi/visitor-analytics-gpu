"""Unit tests for VisitorStatePersistence with encryption."""

import numpy as np
import pytest
from unittest.mock import patch

from visitor_state import (
    VisitorStatePersistence,
    _encrypt_embedding,
    _decrypt_embedding,
)


class TestBodyReIDPersistence:
    def test_save_and_restore_roundtrip(self, tmp_path):
        from visitor_state import VisitorStatePersistence
        import numpy as np
        persistence = VisitorStatePersistence(data_dir=str(tmp_path))

        persons = {
            1: {"embeddings": [np.random.randn(512).astype(np.float32)],
                "timestamp": 1000.0, "gender": "Male",
                "age_obs": [30], "age_group": "Adults"}
        }
        pending = {}
        stats = {"total_visitors": 1, "male": 1, "female": 0, "unknown": 0,
                 "age_groups": {"Children": 0, "Teens": 0, "Young Adults": 0,
                                "Adults": 1, "Seniors": 0, "Unknown": 0}}

        persistence.save_state(persons, pending, stats, next_person_id=2)
        p2, pe2, s2, nid2 = persistence.restore_state()

        assert s2["total_visitors"] == 1
        assert nid2 == 2
        assert len(p2) == 1
        assert 1 in p2
        assert len(p2[1]["embeddings"]) == 1

    def test_restore_missing_file_returns_defaults(self, tmp_path):
        from visitor_state import VisitorStatePersistence
        persistence = VisitorStatePersistence(data_dir=str(tmp_path / "nonexistent"))
        persons, pending, stats, nid = persistence.restore_state()
        assert persons == {}
        assert stats["total_visitors"] == 0
        assert nid == 1


class TestEncryption:
    def test_plain_when_no_key(self):
        """Without EMBEDDING_ENCRYPTION_KEY, embeddings stored as plain lists."""
        with patch("visitor_state._encryption_available", False), \
             patch("visitor_state._fernet", None):
            data = [1.0, 2.0, 3.0]
            result = _encrypt_embedding(data)
            assert isinstance(result, list)
            assert result == data

    def test_encrypt_decrypt_round_trip(self):
        """With encryption, embeddings should round-trip correctly."""
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()

        import visitor_state
        original_fernet = visitor_state._fernet
        original_available = visitor_state._encryption_available

        try:
            visitor_state._fernet = Fernet(key)
            visitor_state._encryption_available = True

            data = [1.0, 2.0, 3.0, 4.0]
            encrypted = _encrypt_embedding(data)
            assert isinstance(encrypted, dict)
            assert encrypted["__encrypted__"] is True

            decrypted = _decrypt_embedding(encrypted)
            np.testing.assert_array_almost_equal(decrypted, data, decimal=5)
        finally:
            visitor_state._fernet = original_fernet
            visitor_state._encryption_available = original_available
