"""测试私聊亲和契约租约（DM Affinity Lease）。"""

import time
from pathlib import Path

import pytest

from gsuid_core.ai_core.persona.config import persona_config_manager
from gsuid_core.ai_core.proactive.dm_lease import (
    DM_LEASE_TTL_SECONDS,
    grant_dm_lease,
    renew_dm_lease,
    revoke_dm_lease,
    get_active_dm_lease,
)


def test_dm_affinity_lease_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    test_file = tmp_path / "dm_leases.json"
    monkeypatch.setattr("gsuid_core.ai_core.proactive.dm_lease._path", lambda: test_file)

    user_id = "test_user_dm_999"
    bot_id = "test_bot_dm"
    configs = persona_config_manager.get_all_configs()
    persona = next(iter(configs.keys())) if configs else "test_persona_dm"

    # 1. 签发租约
    lease = grant_dm_lease(
        user_id=user_id,
        persona_name=persona,
        bot_id=bot_id,
        source_group_id="999888",
    )
    assert lease.persona_name == persona
    assert lease.source_group_id == "999888"
    assert lease.expires_at - lease.issued_at == DM_LEASE_TTL_SECONDS

    # 2. 查询活跃租约（支持 bot_id + user_id 或纯 user_id）
    found = get_active_dm_lease(user_id, bot_id)
    assert found is not None
    assert found.persona_name == persona

    found_by_user = get_active_dm_lease(user_id)
    assert found_by_user is not None
    assert found_by_user.persona_name == persona

    # 3. 续期双写一致性测试：bot_id+user 续期后，纯 user 查找也同步延期
    old_exp = found.expires_at
    time.sleep(0.01)
    renewed = renew_dm_lease(user_id, bot_id)
    assert renewed is True

    found_renewed = get_active_dm_lease(user_id, bot_id)
    assert found_renewed is not None
    assert found_renewed.expires_at >= old_exp

    found_user_renewed = get_active_dm_lease(user_id)
    assert found_user_renewed is not None
    assert found_user_renewed.expires_at == found_renewed.expires_at

    # 4. 撤销租约
    revoked = revoke_dm_lease(user_id, bot_id)
    assert revoked is True
    assert get_active_dm_lease(user_id, bot_id) is None
    assert get_active_dm_lease(user_id) is None


def test_dm_affinity_lease_session_routing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    test_file = tmp_path / "dm_leases.json"
    monkeypatch.setattr("gsuid_core.ai_core.proactive.dm_lease._path", lambda: test_file)

    configs = persona_config_manager.get_all_configs()
    assert configs, "至少应有一个可用 persona"
    persona = next(iter(configs.keys()))

    user_id = "test_user_routing_101"
    bot_id = "mock_bot"

    grant_dm_lease(user_id=user_id, persona_name=persona, bot_id=bot_id)
    session_id = f"mock_ws:{bot_id}:mock_self:private:{user_id}"
    resolved = persona_config_manager.get_persona_for_session(session_id)
    assert resolved == persona


def test_dm_affinity_lease_zombie_eviction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    test_file = tmp_path / "dm_leases.json"
    monkeypatch.setattr("gsuid_core.ai_core.proactive.dm_lease._path", lambda: test_file)

    grant_dm_lease(user_id="u_zombie", persona_name="nonexistent_persona_xyz", bot_id="bot1")
    assert get_active_dm_lease("u_zombie", "bot1") is not None

    renewed = renew_dm_lease("u_zombie", "bot1")
    assert renewed is False
    assert get_active_dm_lease("u_zombie", "bot1") is None
