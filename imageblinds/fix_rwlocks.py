"""Workaround for an openjiuwen + filelock interaction bug.

openjiuwen's ``HybridAsyncReadWriteLock`` acquires the underlying filelock in
one asyncio task (``asyncio.create_task(acquire(...))``) and releases it in a
different task (``asyncio.create_task(release())``). filelock 4.x tracks lock
ownership per task, so the release always raises "Cannot release a lock ...
that is not held by this task", the OS-level SQLite lock is never released,
``close()`` then fails with "Cannot close an active file lock", and the next
request to touch the same path polls for the full lock timeout (300s) —
blocking the app.

Acquiring and releasing in the *same* task (what filelock expects) fixes the
leak. Patch before any openjiuwen filesystem operation runs.
"""

from __future__ import annotations

import asyncio

from filelock import Timeout as FileLockTimeout


def patch() -> None:
    try:
        from openjiuwen.core.sys_operation.local import _async_read_write_lock as module
    except ImportError:
        return

    async def _acquire_file_same_task(self, mode: str, deadline: float) -> None:
        acquire = self._file.acquire_read if mode == "read" else self._file.acquire_write
        while True:
            try:
                await acquire(timeout=0, blocking=False)
                return
            except FileLockTimeout:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise
                await asyncio.sleep(min(self._poll_interval, remaining))

    async def _release_file_same_task(self) -> None:
        await self._file.release()

    module.HybridAsyncReadWriteLock._acquire_file = _acquire_file_same_task
    module.HybridAsyncReadWriteLock._release_file = _release_file_same_task
