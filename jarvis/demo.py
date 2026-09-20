"""Run with python -m jarvis.demo [--cancel]. Synthetic data only."""

import argparse
import asyncio
from .core import Coordinator, Request, Stage
from .simulated import SimulatedWorker


async def demo(cancel: bool) -> None:
    implementation = SimulatedWorker("Simulated implementation completed", delay=0.05)
    review = SimulatedWorker("Simulated review passed")
    coordinator = Coordinator((Stage("implementation", implementation), Stage("review", review)))
    task_id = coordinator.submit(Request("synthetic-fixture", "Exercise task handoff"), "demo-1")
    if cancel:
        await implementation.started.wait()
        await coordinator.cancel(task_id)
    await coordinator.wait(task_id)
    print("SIMULATION ONLY — no agents, APIs, files or microphone used")
    for event in coordinator.events(task_id):
        print(f"{event.sequence}: {event.kind}" + (f" ({event.stage})" if event.stage else ""))
    print(f"Final status: {coordinator.status(task_id).value}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cancel", action="store_true")
    asyncio.run(demo(parser.parse_args().cancel))
