"""Unit tests for VisitorStatePersistence with encryption."""

import numpy as np
import pytest
from unittest.mock import patch

from visitor_state import (
    VisitorStatePersistence,
    _encrypt_embedding,
    _decrypt_embedding,
)


class TestPersistenceRoundTrip:
    def test_save_and_load(self, tmp_path):
        persist = VisitorStatePersistence(data_dir=str(tmp_path))

        visitors = {
            1: {
                "embeddings": [np.random.randn(512).astype(np.float32)],
                "timestamp": 1000.0,
                "gender": "Male",
                "age_group": "Adults",
            }
        }
        stats = {
            "total_visitors": 1, "male": 1, "female": 0, "unknown": 0,
            "age_groups": {
                "Children": 0, "Teens": 0, "Young Adults": 0,
                "Adults": 1, "Seniors": 0, "Unknown": 0,
            },
        }

        persist.save_state(visitors, {}, stats, 2, 1)
        state = persist.load_state()

        assert state["stats"]["total_visitors"] == 1
        assert len(state["visitors"]) == 1
        restored_emb = list(state["visitors"].values())[0]["embeddings"][0]
        assert isinstance(restored_emb, np.ndarray)
        assert restored_emb.shape == (512,)

    def test_load_missing_file(self, tmp_path):
        persist = VisitorStatePersistence(data_dir=str(tmp_path))
        state = persist.load_state()
        assert state["stats"]["total_visitors"] == 0
        assert state["next_visitor_id"] == 1


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
