import pytest

from app.middleware import token_cache


@pytest.fixture(autouse=True)
def _clean_cache():
    token_cache.clear_token_cache()
    yield
    token_cache.clear_token_cache()


def test_get_cached_user_id_returns_none_for_unknown_token():
    assert token_cache.get_cached_user_id("never-cached") is None


def test_cache_token_then_get_returns_same_user_id_within_ttl():
    token_cache.cache_token("tok-1", "user-1")

    assert token_cache.get_cached_user_id("tok-1") == "user-1"


def test_cache_key_is_hashed_never_the_raw_token():
    token_cache.cache_token("super-secret-raw-token", "user-1")

    assert "super-secret-raw-token" not in token_cache._token_cache
    assert token_cache._hash_token("super-secret-raw-token") in token_cache._token_cache


def test_get_cached_user_id_expires_after_ttl(monkeypatch):
    fake_now = 1000.0
    monkeypatch.setattr(token_cache.time, "monotonic", lambda: fake_now)
    token_cache.cache_token("tok-1", "user-1")
    assert token_cache.get_cached_user_id("tok-1") == "user-1"

    fake_now += token_cache.TOKEN_CACHE_TTL_SECONDS + 1

    assert token_cache.get_cached_user_id("tok-1") is None


def test_expired_entry_is_purged_from_dict_on_lookup(monkeypatch):
    fake_now = 1000.0
    monkeypatch.setattr(token_cache.time, "monotonic", lambda: fake_now)
    token_cache.cache_token("tok-1", "user-1")
    key = token_cache._hash_token("tok-1")
    assert key in token_cache._token_cache

    fake_now += token_cache.TOKEN_CACHE_TTL_SECONDS + 1
    token_cache.get_cached_user_id("tok-1")

    assert key not in token_cache._token_cache


def test_invalidate_cached_token_removes_entry_immediately():
    token_cache.cache_token("tok-1", "user-1")
    assert token_cache.get_cached_user_id("tok-1") == "user-1"

    token_cache.invalidate_cached_token("tok-1")

    assert token_cache.get_cached_user_id("tok-1") is None


def test_invalidate_cached_token_is_a_noop_for_unknown_token():
    token_cache.invalidate_cached_token("never-cached")  # no debe lanzar


def test_cache_evicts_expired_entries_on_insert_before_checking_cap(monkeypatch):
    fake_now = 1000.0
    monkeypatch.setattr(token_cache.time, "monotonic", lambda: fake_now)
    monkeypatch.setattr(token_cache, "TOKEN_CACHE_MAX_ENTRIES", 3)

    token_cache.cache_token("tok-1", "user-1")
    token_cache.cache_token("tok-2", "user-2")

    fake_now += token_cache.TOKEN_CACHE_TTL_SECONDS + 1  # tok-1/tok-2 ya vencidos

    # Si la eviccion de vencidas al insertar funciona, este par nuevo no deberia
    # disparar el clear-por-cap (las vencidas se limpian antes de contar el cap).
    token_cache.cache_token("tok-3", "user-3")
    token_cache.cache_token("tok-4", "user-4")

    assert token_cache.get_cached_user_id("tok-3") == "user-3"
    assert token_cache.get_cached_user_id("tok-4") == "user-4"
    assert token_cache.get_cached_user_id("tok-1") is None
    assert token_cache.get_cached_user_id("tok-2") is None


def test_cache_clears_entirely_when_cap_exceeded_by_still_live_entries(monkeypatch):
    monkeypatch.setattr(token_cache, "TOKEN_CACHE_MAX_ENTRIES", 2)

    token_cache.cache_token("tok-1", "user-1")
    token_cache.cache_token("tok-2", "user-2")
    # Ambas siguen vivas (nada vencio): al llegar al cap, el proximo insert
    # limpia todo el dict en vez de mantener una politica de eviccion parcial.
    token_cache.cache_token("tok-3", "user-3")

    assert token_cache.get_cached_user_id("tok-1") is None
    assert token_cache.get_cached_user_id("tok-2") is None
    assert token_cache.get_cached_user_id("tok-3") == "user-3"
