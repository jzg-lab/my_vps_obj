"""Bounded in-process coordination checks; no database fixture or PostgreSQL claims."""

import asyncio
from unittest import IsolatedAsyncioTestCase

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.dal.resource_operations_dal import coordinate_resources


class SQLiteResourceCoordinationTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite://")
        self.sessions = async_sessionmaker(self.engine)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_nested_shared_sessions_do_not_wait_on_each_other(self) -> None:
        async with asyncio.timeout(2), self.sessions() as outer:
            await coordinate_resources(outer)
            async with self.sessions() as nested:
                await coordinate_resources(nested)
                await coordinate_resources(nested)
                self.assertEqual(nested.info["resource_coordination"], "shared")
            self.assertEqual(outer.info["resource_coordination"], "shared")
            with self.assertRaisesRegex(RuntimeError, "resource_lock_order"):
                await coordinate_resources(outer, exclusive=True)

    async def test_exclusive_waits_for_all_readers_and_outer_transaction_end(self) -> None:
        async with (
            asyncio.timeout(2),
            self.sessions() as first,
            self.sessions() as second,
            self.sessions() as writer,
        ):
            await coordinate_resources(first)
            await coordinate_resources(second)
            savepoint = await second.begin_nested()
            async with asyncio.TaskGroup() as tasks:
                waiting = tasks.create_task(coordinate_resources(writer, exclusive=True))
                await asyncio.sleep(0)
                self.assertFalse(waiting.done())
                await first.commit()
                await savepoint.rollback()
                await asyncio.sleep(0)
                self.assertFalse(waiting.done())
                await second.rollback()
                await waiting
            self.assertEqual(writer.info["resource_coordination"], "exclusive")

    async def test_exclusive_blocks_both_modes_without_leaking_cancelled_waiters(self) -> None:
        for exclusive in (False, True):
            with self.subTest(exclusive=exclusive):
                async with (
                    asyncio.timeout(2),
                    self.sessions() as holder,
                    self.sessions() as waiter,
                    self.sessions() as next_session,
                ):
                    await coordinate_resources(holder, exclusive=True)
                    async with asyncio.TaskGroup() as tasks:
                        waiting = tasks.create_task(
                            coordinate_resources(waiter, exclusive=exclusive)
                        )
                        await asyncio.sleep(0)
                        self.assertFalse(waiting.done())
                        waiting.cancel()
                        with self.assertRaises(asyncio.CancelledError):
                            await waiting
                    self.assertNotIn("resource_coordination", waiter.info)
                    await holder.rollback()
                    await coordinate_resources(next_session, exclusive=exclusive)

    async def test_cancelled_shared_holder_releases_its_transaction_lock(self) -> None:
        acquired = asyncio.Event()

        async def hold() -> None:
            async with self.sessions() as session:
                await coordinate_resources(session)
                acquired.set()
                await asyncio.Event().wait()

        async with asyncio.timeout(2), asyncio.TaskGroup() as tasks:
            holder = tasks.create_task(hold())
            await acquired.wait()
            holder.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await holder
            async with self.sessions() as writer:
                await coordinate_resources(writer, exclusive=True)
