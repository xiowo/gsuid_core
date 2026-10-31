from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlmodel import SQLModel, select
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import gsuid_core.ai_core.rag.base as rag_base
from gsuid_core.utils.database import base_models
from gsuid_core.webconsole.ai_memory_api import delete_scope_memory
from gsuid_core.ai_core.memory.database.models import (
    AIMemEdge,
    AIMemEntity,
    AIMemEpisode,
    AIMemCategory,
)


async def _seed(maker: async_sessionmaker[AsyncSession], target_scope: str, other_scope: str) -> None:
    async with maker() as session:
        session.add(
            AIMemEpisode(
                scope_key=target_scope,
                speaker_ids=["user1"],
                content="测试对话内容",
                qdrant_id="qep_1",
            )
        )
        ent1 = AIMemEntity(
            id="ent_1",
            scope_key=target_scope,
            name="实体A",
            summary="测试实体A",
            qdrant_id="qent_1",
        )
        ent2 = AIMemEntity(
            id="ent_2",
            scope_key=target_scope,
            name="实体B",
            summary="测试实体B",
            qdrant_id="qent_2",
        )
        session.add(ent1)
        session.add(ent2)
        session.add(
            AIMemEdge(
                scope_key=target_scope,
                source_entity_id="ent_1",
                target_entity_id="ent_2",
                fact="A与B有关",
                qdrant_id="qedge_1",
            )
        )
        session.add(
            AIMemCategory(
                scope_key=target_scope,
                name="类目1",
                layer=0,
            )
        )
        session.add(
            AIMemEpisode(
                scope_key=other_scope,
                speaker_ids=["user2"],
                content="其他群对话内容",
                qdrant_id="qep_2",
            )
        )
        await session.commit()


def test_delete_scope_memory_clears_scope_and_preserves_others(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asyncio.run(_delete_scope_memory_clears_scope_and_preserves_others(tmp_path, monkeypatch))


async def _delete_scope_memory_clears_scope_and_preserves_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target_scope = "group:277045897"
    other_scope = "group:5099998"

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'mem.db').as_posix()}",
        poolclass=NullPool,
        connect_args={"check_same_thread": False, "timeout": 5.0},
    )
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(base_models, "async_maker", maker)
    monkeypatch.setattr(rag_base, "client", None)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        await _seed(maker, target_scope, other_scope)

        data = await delete_scope_memory(target_scope, _={"username": "admin"})
        assert data["status"] == 0
        assert data["msg"] == "ok"
        assert data["data"]["scope_key"] == target_scope
        assert data["data"]["deleted_episodes"] == 1
        assert data["data"]["deleted_entities"] == 2
        assert data["data"]["deleted_edges"] == 1
        assert data["data"]["deleted_categories"] == 1

        async with maker() as session:
            target_eps = (
                (await session.execute(select(AIMemEpisode).where(AIMemEpisode.scope_key == target_scope)))
                .scalars()
                .all()
            )
            assert len(target_eps) == 0

            other_eps = (
                (await session.execute(select(AIMemEpisode).where(AIMemEpisode.scope_key == other_scope)))
                .scalars()
                .all()
            )
            assert len(other_eps) == 1
    finally:
        await engine.dispose()
