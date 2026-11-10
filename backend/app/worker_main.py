"""Standalone durable AI queue worker for one ECS worker task."""

import asyncio
import signal

from app.config import settings
from app.database import SessionLocal, engine
from app.services.ai.worker import run_worker


async def main() -> None:
    worker = asyncio.create_task(run_worker(SessionLocal, settings), name="kinetix-ai-worker")
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, worker.cancel)
        except NotImplementedError:
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(worker.cancel))
    try:
        await worker
    except asyncio.CancelledError:
        pass
    finally:
        engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
