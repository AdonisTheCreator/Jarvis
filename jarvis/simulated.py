"""In-process test worker. Executes no commands and changes no project files."""

import asyncio
from .core import Request, Result


class SimulatedWorker:
    def __init__(self, summary: str, delay: float = 0.01, success: bool = True):
        self.summary = summary
        self.delay = delay
        self.success = success
        self.calls: list[tuple[str, Result | None]] = []
        self.started = asyncio.Event()
        self._stopped: set[str] = set()

    async def run(self, task_id: str, request: Request, prior: Result | None) -> Result:
        self.calls.append((task_id, prior))
        self.started.set()
        await asyncio.sleep(self.delay)
        if task_id in self._stopped:
            return Result(False, "Simulation stopped")
        return Result(self.success, self.summary, ("simulation://result",))

    async def cancel(self, task_id: str) -> bool:
        self._stopped.add(task_id)
        # There is no external process or side effect to stop in this simulation.
        return True
