from app.core.security import hash_password, verify_password


def test_hash_password_returns_hash_different_from_plaintext():

    password = "password123"
    hashed_password = hash_password(password)

    assert hashed_password != password
    assert isinstance(hashed_password, str)


def test_verify_password_returns_true_for_correct_password():

    password = "password123"
    hashed_password = hash_password(password)

    assert verify_password(password, hashed_password) is True


def test_verify_password_returns_false_for_incorrect_password():

    password = "password123"
    hashed_password = hash_password(password)

    wrong_password = "random_password"

    assert verify_password(wrong_password, hashed_password) is False


def test_hash_password_produces_different_hashes_for_same_password():

    password = "password123"

    hashed_password_one = hash_password(password)
    hashed_password_two = hash_password(password)

    assert hashed_password_one != hashed_password_two
    assert verify_password(password, hashed_password_two) is True
