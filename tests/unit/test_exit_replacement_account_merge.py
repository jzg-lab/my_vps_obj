"""Real SQLite queries for both merge participants; no PostgreSQL lock-concurrency claim."""

import pytest
from sqlalchemy import func, select

from db.dal.service_accounts_dal import guard_replacement_merge
from db.dal.user_merge_dal import UserMergeConflictError, merge_users
from db.dal.user_services_dal import ServiceConflict
from db.models import User
from db.service_models import ServiceOrder
from tests.unit.test_service_exit_replacement import ReplacementDatabaseTestCase


class ExitReplacementAccountMergeTests(ReplacementDatabaseTestCase):
    async def test_source_or_target_replacement_blocks_merge_without_changing_ownership(
        self,
    ) -> None:
        async with self.sessions.begin() as session:
            state = await self.state(session)
            state.connection.sync_pending = False
            order_count = await session.scalar(select(func.count()).select_from(ServiceOrder))

        for source_id, target_id in ((1, 2), (2, 1)):
            with self.subTest(source_id=source_id, target_id=target_id):
                async with self.sessions.begin() as session:
                    with pytest.raises(ServiceConflict, match="exit_replacement_in_progress"):
                        await guard_replacement_merge(session, source_id, target_id)
                    with pytest.raises(UserMergeConflictError) as raised:
                        await merge_users(
                            session, source_user_id=source_id, target_user_id=target_id
                        )
                    assert raised.value.code == "exit_replacement_in_progress"
                    assert raised.value.message_key == "wa_auth_access_denied"
                async with self.sessions() as session:
                    state = await self.state(session)
                    assert await session.get(User, source_id) is not None
                    assert await session.get(User, target_id) is not None
                    assert state.service.user_id == 1 and state.order.user_id == 1
                    assert state.order.request_owner_id == state.execution.request_owner_id == 1
                    assert state.connection.replacement_order_id == state.order.id
                    assert state.connection.sync_pending is False
                    assert state.old_exit.service_id == state.service.id
                    assert state.new_exit.hold_order_id == state.order.id
                    assert (
                        await session.scalar(select(func.count()).select_from(ServiceOrder))
                        == order_count
                    )
        assert not self.panel.mock_calls

    async def test_other_accounts_replacement_does_not_block_unrelated_merge_guard(self) -> None:
        async with self.sessions() as session:
            assert await session.get(User, 2) is not None
            assert await session.get(User, 3) is not None
            await guard_replacement_merge(session, 2, 3)
            await guard_replacement_merge(session, 3, 2)
            state = await self.state(session)
            assert state.connection.replacement_order_id == state.order.id
