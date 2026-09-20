import asyncio
import unittest

from jarvis.core import Coordinator, Request, Stage, Status
from jarvis.simulated import SimulatedWorker


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.request = Request("synthetic-project", "Synthetic implementation task")
        self.implement = SimulatedWorker("implementation")
        self.review = SimulatedWorker("review")
        self.coordinator = Coordinator((Stage("implement", self.implement), Stage("review", self.review)))

    async def test_handoff_and_duplicate_delivery(self):
        task = self.coordinator.submit(self.request, "same-logical-request")
        duplicate = self.coordinator.submit(self.request, "same-logical-request")
        self.assertEqual(task, duplicate)
        self.assertEqual(await self.coordinator.wait(task), Status.SUCCEEDED)
        self.assertEqual(len(self.implement.calls), 1)
        self.assertEqual(self.review.calls[0][1].summary, "implementation")
        self.assertEqual(self.coordinator.result(task).summary, "review")
        self.assertEqual([e.kind for e in self.coordinator.events(task)], [
            "queued", "running", "stage_started", "stage_completed",
            "stage_started", "stage_completed", "succeeded",
        ])
        # A retry after completion must not repeat side effects either.
        self.assertEqual(self.coordinator.submit(self.request, "same-logical-request"), task)

    async def test_key_cannot_be_reused_for_different_instruction(self):
        task = self.coordinator.submit(self.request, "key")
        with self.assertRaises(ValueError):
            self.coordinator.submit(Request("other-project", "other task"), "key")
        await self.coordinator.wait(task)

    async def test_cancel_before_launch_starts_no_worker(self):
        task = self.coordinator.submit(self.request, "key")
        self.assertEqual(await self.coordinator.cancel(task), Status.CANCELLED)
        self.assertEqual(self.implement.calls, [])
        self.assertEqual(self.review.calls, [])
        self.assertEqual(await self.coordinator.wait(task), Status.CANCELLED)

    async def test_cancel_implementation_prevents_review(self):
        self.implement.delay = 10
        task = self.coordinator.submit(self.request, "key")
        await self.implement.started.wait()
        statuses = await asyncio.gather(self.coordinator.cancel(task), self.coordinator.cancel(task))
        self.assertEqual(statuses, [Status.CANCELLED, Status.CANCELLED])
        self.assertEqual(self.review.calls, [])
        self.assertEqual([e.kind for e in self.coordinator.events(task)].count("cancelled"), 1)

    async def test_cancel_review_and_late_result_cannot_report_success(self):
        self.review.delay = 10
        task = self.coordinator.submit(self.request, "key")
        await self.review.started.wait()
        self.assertEqual(await self.coordinator.cancel(task), Status.CANCELLED)
        self.assertNotIn("succeeded", [e.kind for e in self.coordinator.events(task)])

    async def test_failed_implementation_never_starts_review(self):
        self.implement.success = False
        task = self.coordinator.submit(self.request, "key")
        self.assertEqual(await self.coordinator.wait(task), Status.FAILED)
        self.assertEqual(self.review.calls, [])

    async def test_failed_review_is_not_success(self):
        self.review.success = False
        task = self.coordinator.submit(self.request, "key")
        self.assertEqual(await self.coordinator.wait(task), Status.FAILED)

    async def test_unconfirmed_cancel_blocks_new_work(self):
        async def unconfirmed(_):
            return False
        self.implement.cancel = unconfirmed
        self.implement.delay = 10
        task = self.coordinator.submit(self.request, "key")
        await self.implement.started.wait()
        self.assertEqual(await self.coordinator.cancel(task), Status.UNKNOWN)
        with self.assertRaises(RuntimeError):
            self.coordinator.submit(self.request, "new-occasion")
        self.assertEqual(self.review.calls, [])

    async def test_cancel_timeout_is_unknown(self):
        async def slow_cancel(_):
            await asyncio.sleep(10)
            return True
        self.implement.cancel = slow_cancel
        self.implement.delay = 10
        coordinator = Coordinator((Stage("implement", self.implement),), cancel_timeout=0.01)
        task = coordinator.submit(self.request, "key")
        await self.implement.started.wait()
        self.assertEqual(await coordinator.cancel(task), Status.UNKNOWN)

    async def test_transport_failure_is_unknown_not_completed(self):
        async def disconnected(*_):
            raise ConnectionError("synthetic disconnect")
        self.implement.run = disconnected
        task = self.coordinator.submit(self.request, "key")
        self.assertEqual(await self.coordinator.wait(task), Status.UNKNOWN)
        self.assertEqual(self.review.calls, [])

    async def test_waiter_timeout_does_not_cancel_work(self):
        task = self.coordinator.submit(self.request, "key")
        with self.assertRaises(TimeoutError):
            await asyncio.wait_for(self.coordinator.wait(task), timeout=0.001)
        self.assertEqual(await self.coordinator.wait(task), Status.SUCCEEDED)

    async def test_cancelling_completed_task_preserves_result(self):
        task = self.coordinator.submit(self.request, "key")
        await self.coordinator.wait(task)
        self.assertEqual(await self.coordinator.cancel(task), Status.SUCCEEDED)


if __name__ == "__main__":
    unittest.main()
