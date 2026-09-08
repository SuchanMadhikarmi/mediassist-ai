# ============================================================
# backend/tests/test_auth.py
# Deterministic tests for password hashing (Phase 3, AuthN).
#
# WHY: passwords must never be stored in plaintext (classic student
# mistake / audit failure). These tests pin that we hash with a one-way
# salt (bcrypt) and verify WITHOUT ever comparing plaintext strings.
# ============================================================

from security.auth import hash_password, verify_password


class TestPasswordHashing:
    def test_hash_differs_from_plaintext(self):
        hashed = hash_password("admin123")
        assert hashed != "admin123"
        assert hashed.startswith("$2")  # bcrypt salt prefix

    def test_same_password_twice_gives_different_hashes(self):
        # bcrypt salts each hash → two hashes of the same password differ.
        assert hash_password("admin123") != hash_password("admin123")

    def test_verify_roundtrip(self):
        hashed = hash_password("s3cret!")
        assert verify_password("s3cret!", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("s3cret!")
        assert verify_password("wrong", hashed) is False

    def test_verify_empty_password_against_hashed_empty(self):
        hashed = hash_password("")
        assert verify_password("", hashed) is True