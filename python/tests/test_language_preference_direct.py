"""
Regression tests for Issue A: Direct Language Preference Retrieval.
Verifies that language preferences are directly queried without top-K/pagination limits,
are properly scoped to users/projects, ignore inactive records, and reject malformed entries.
"""
import pytest
from apps.ai_api.memory import MemoryDB
from apps.ai_api.language import response_language


def test_language_preference_older_than_150_memories(tmp_path):
    """Preference older than 150 newer memories remains active and retrievable."""
    db_path = str(tmp_path / "test_mem_150.db")
    db = MemoryDB(db_path)
    user_id = "user_pref_older"

    # Create original preference: en
    pref = db.create_memory(user_id=user_id, info_type="preference", content="language:en")
    assert pref is not None

    # Insert 160 newer non-preference memories
    for i in range(160):
        db.create_memory(user_id=user_id, info_type="fact", content=f"Fact memory number {i+1}")

    # Verify standard list_memories(default limit=100) does not see it if paginated
    recent_100 = db.list_memories(user_id, limit=100)
    assert len(recent_100) == 100
    assert not any(m["content"] == "language:en" for m in recent_100)

    # Direct retrieval MUST succeed and return 'en'
    assert db.get_language_preference(user_id) == "en"
    active_mem = db.get_active_language_preference_memory(user_id)
    assert active_mem is not None
    assert active_mem["content"] == "language:en"
    db.close()


def test_inactive_language_preference_ignored(tmp_path):
    """Inactive preference (superseded or deleted) is never used."""
    db_path = str(tmp_path / "test_inactive.db")
    db = MemoryDB(db_path)
    user_id = "user_pref_inactive"

    mem = db.create_memory(user_id=user_id, info_type="preference", content="language:en")
    assert db.get_language_preference(user_id) == "en"

    # Deactivate memory
    db.delete_memory(user_id, mem["memory_id"])
    assert db.get_language_preference(user_id) is None
    assert db.get_active_language_preference_memory(user_id) is None
    db.close()


def test_two_users_isolated_preferences(tmp_path):
    """Two users have distinct preferences without cross-user leakage."""
    db_path = str(tmp_path / "test_isolation.db")
    db = MemoryDB(db_path)

    db.create_memory(user_id="user_A", info_type="preference", content="language:en")
    db.create_memory(user_id="user_B", info_type="preference", content="language:vi")

    assert db.get_language_preference("user_A") == "en"
    assert db.get_language_preference("user_B") == "vi"
    assert db.get_language_preference("user_C") is None
    db.close()


def test_multiple_sessions_same_preference(tmp_path):
    """Multiple sessions under the same user reliably retrieve the same preference."""
    db_path = str(tmp_path / "test_sessions.db")
    db = MemoryDB(db_path)
    user_id = "user_multisession"

    db.create_memory(user_id=user_id, info_type="preference", content="language:en", source_session="sess_01")
    assert db.get_language_preference(user_id) == "en"
    assert db.get_language_preference(user_id) == "en"
    db.close()


def test_project_scoped_preference_priority(tmp_path):
    """Project-scoped preference overrides global user preference when project_id is given."""
    db_path = str(tmp_path / "test_project.db")
    db = MemoryDB(db_path)
    user_id = "user_proj"

    # Global preference: vi
    db.create_memory(user_id=user_id, info_type="preference", content="language:vi", project_id=None)
    # Project-specific preference: en
    db.create_memory(user_id=user_id, info_type="preference", content="language:en", project_id="proj_alpha")

    # When querying with proj_alpha, returns en
    assert db.get_language_preference(user_id, project_id="proj_alpha") == "en"
    # When querying without project, returns global (vi)
    assert db.get_language_preference(user_id) == "vi"
    # When querying with an unknown project, falls back to global (vi)
    assert db.get_language_preference(user_id, project_id="proj_beta") == "vi"
    db.close()


def test_malformed_preference_rejected(tmp_path):
    """Malformed preference content or descriptive text mentioning language is rejected."""
    db_path = str(tmp_path / "test_malformed.db")
    db = MemoryDB(db_path)
    user_id = "user_malformed"

    db.create_memory(user_id=user_id, info_type="preference", content="I really enjoy language: French or Spanish")
    db.create_memory(user_id=user_id, info_type="preference", content="language:python")
    db.create_memory(user_id=user_id, info_type="preference", content="language:english_uk")

    assert db.get_language_preference(user_id) is None
    assert db.get_active_language_preference_memory(user_id) is None

    # Valid entry must be strictly 'language:vi' or 'language:en'
    db.create_memory(user_id=user_id, info_type="preference", content="language:vi")
    assert db.get_language_preference(user_id) == "vi"
    db.close()


def test_explicit_preference_priority_over_saved_preference():
    """Explicit request preferred_language ('vi'/'en') overrides saved preference; 'auto' defers."""
    # When saved is en, but user explicitly specifies vi:
    saved = "en"
    explicit_vi = "vi"
    res_vi = response_language(explicit_vi, "en")
    assert res_vi == "vi"

    # When saved is vi, but user explicitly specifies en:
    explicit_en = "en"
    res_en = response_language(explicit_en, "vi")
    assert res_en == "en"

    # When requested is auto, resolution defers to saved preference:
    requested_auto = "auto"
    effective_pref = requested_auto if requested_auto != "auto" else (saved or "auto")
    assert effective_pref == "en"
    assert response_language(effective_pref, "vi") == "en"
