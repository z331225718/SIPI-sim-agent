from __future__ import annotations

import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-runtime" / "src"))

from sipi_runtime import InMemoryEventSink, InMemoryLifecycle, InvalidTransition
from sipi_contracts import parse_success_manifest


class LifecycleTests(unittest.TestCase):
    def active(self, specs: dict[str, bool | dict[str, bool]] | None = None) -> InMemoryLifecycle:
        lifecycle = InMemoryLifecycle("run-1", specs or {"required": True, "optional": False})
        lifecycle.start_resolving()
        lifecycle.activate_execution()
        return lifecycle

    def ready(self, lifecycle: InMemoryLifecycle, node_id: str = "required") -> None:
        lifecycle.mark_node_ready(node_id)

    def publish(self, lifecycle: InMemoryLifecycle, attempt_id: str) -> None:
        for stage in ("validating", "staging", "running", "publishing"):
            lifecycle.advance_attempt(attempt_id, stage)

    def manifest(self, analysis_id: str, *, run_id: str = "source-run"):
        return parse_success_manifest(
            {
                "schema": "sipi.success-manifest.v1",
                "run_id": run_id,
                "analysis_id": analysis_id,
                "attempt_id": "cached-attempt",
                "run_record_sha256": "0" * 64,
                "checksums_sha256": "1" * 64,
                "artifacts": [],
                "extensions": {},
            }
        )

    def test_execution_and_node_transitions_are_one_way(self) -> None:
        lifecycle = InMemoryLifecycle("run-1", {"a": True})
        with self.assertRaises(InvalidTransition):
            lifecycle.activate_execution()
        lifecycle.start_resolving()
        lifecycle.activate_execution()
        lifecycle.mark_node_ready("a")
        token = lifecycle.start_attempt("a", "a-1")
        self.publish(lifecycle, "a-1")
        lifecycle.finish_attempt("a-1", "succeeded")
        self.assertFalse(token.requested)
        with self.assertRaises(InvalidTransition):
            lifecycle.mark_node_ready("a")
        self.assertEqual(lifecycle.finalize_execution(), "succeeded")
        with self.assertRaises(InvalidTransition):
            lifecycle.start_resolving()

    def test_attempt_order_retry_and_single_active_attempt(self) -> None:
        lifecycle = self.active()
        self.ready(lifecycle)
        lifecycle.start_attempt("required", "a-1")
        with self.assertRaises(InvalidTransition):
            lifecycle.advance_attempt("a-1", "running")
        with self.assertRaises(InvalidTransition):
            lifecycle.start_attempt("required", "a-2")
        lifecycle.finish_attempt("a-1", "failed", retry_allowed=True)
        lifecycle.start_attempt("required", "a-2")
        lifecycle.finish_attempt("a-2", "failed")
        with self.assertRaises(InvalidTransition):
            lifecycle.start_attempt("required", "a-3")

    def test_blocked_and_cache_hit_never_create_attempts(self) -> None:
        lifecycle = self.active({"upstream": True, "blocked": True, "cached": True})
        lifecycle.mark_node_ready("upstream")
        lifecycle.start_attempt("upstream", "upstream-1")
        lifecycle.finish_attempt("upstream-1", "failed")
        lifecycle.block_node("blocked", blocked_by=("upstream",))
        lifecycle.mark_node_ready("cached")
        lifecycle.mark_cache_hit("cached", self.manifest("cached"))
        snapshot = lifecycle.snapshot()
        self.assertEqual(snapshot.nodes["blocked"]["blocked_by"], ("upstream",))
        self.assertEqual(snapshot.nodes["cached"]["attempts"], ())
        self.assertTrue(snapshot.nodes["cached"]["cache_hit"])
        self.assertEqual(snapshot.nodes["cached"]["success_manifest"]["run_id"], "source-run")
        self.assertEqual(lifecycle.finalize_execution(), "failed")

    def test_blocked_requires_real_terminal_dependency(self) -> None:
        lifecycle = self.active({"upstream": True, "downstream": True})
        with self.assertRaises(InvalidTransition):
            lifecycle.block_node("downstream", blocked_by=("upstream",))
        with self.assertRaises(InvalidTransition):
            lifecycle.block_node("downstream", blocked_by=("downstream",))
        with self.assertRaises(InvalidTransition):
            lifecycle.block_node("downstream", blocked_by=("missing",))

    def test_cancel_is_one_way_and_unsolicited_cancel_is_a_failure(self) -> None:
        lifecycle = self.active()
        self.ready(lifecycle)
        token = lifecycle.start_attempt("required", "a-1")
        self.assertEqual(lifecycle.request_cancel("required"), "accepted")
        self.assertTrue(token.requested)
        self.assertEqual(lifecycle.request_cancel("required"), "already_requested")
        lifecycle.finish_attempt("a-1", "cancelled")
        lifecycle.mark_node_ready("optional")
        lifecycle.request_cancel("optional")
        self.assertEqual(lifecycle.finalize_execution(), "cancelled")

        protocol = self.active({"a": True})
        protocol.mark_node_ready("a")
        protocol.start_attempt("a", "a-1")
        protocol.finish_attempt("a-1", "cancelled")
        self.assertEqual(protocol.snapshot().attempts["a-1"]["error_category"], "EngineProtocolFailure")
        self.assertEqual(protocol.finalize_execution(), "failed")

    def test_project_cancel_fans_out_and_is_idempotent(self) -> None:
        lifecycle = self.active({"a": True, "b": False, "c": False})
        self.ready(lifecycle, "a")
        self.ready(lifecycle, "b")
        first = lifecycle.start_attempt("a", "a-1")
        second = lifecycle.start_attempt("b", "b-1")
        self.assertEqual(lifecycle.request_cancel(), "accepted")
        self.assertTrue(first.requested)
        self.assertTrue(second.requested)
        self.assertEqual(lifecycle.request_cancel(), "already_requested")
        lifecycle.finish_attempt("a-1", "cancelled")
        lifecycle.finish_attempt("b-1", "cancelled")
        self.assertEqual(lifecycle.snapshot().nodes["c"]["status"], "cancelled")
        self.assertEqual(lifecycle.finalize_execution(), "cancelled")

    def test_queued_and_terminal_cancellation_are_deterministic(self) -> None:
        lifecycle = InMemoryLifecycle("run-1", {"a": True})
        self.assertEqual(lifecycle.request_cancel(), "accepted")
        self.assertEqual(lifecycle.snapshot().execution_status, "resolving")
        self.assertTrue(lifecycle.snapshot().cancel_requested)
        self.assertEqual(lifecycle.finalize_execution(), "cancelled")
        self.assertEqual(lifecycle.request_cancel(), "already_terminal")

    def test_cancel_first_cannot_publish_success(self) -> None:
        lifecycle = self.active({"a": True})
        lifecycle.mark_node_ready("a")
        lifecycle.start_attempt("a", "a-1")
        self.publish(lifecycle, "a-1")
        self.assertEqual(lifecycle.request_cancel("a"), "accepted")
        event_count = len(lifecycle.event_sink.events())
        with self.assertRaises(InvalidTransition):
            lifecycle.finish_attempt("a-1", "succeeded")
        self.assertEqual(len(lifecycle.event_sink.events()), event_count)
        lifecycle.finish_attempt("a-1", "cancelled")
        self.assertEqual(lifecycle.finalize_execution(), "cancelled")

    def test_accepted_required_cancel_wins_over_late_failure(self) -> None:
        lifecycle = self.active({"a": True})
        lifecycle.mark_node_ready("a")
        lifecycle.start_attempt("a", "a-1")
        lifecycle.request_cancel("a")
        lifecycle.finish_attempt("a-1", "failed", retry_allowed=True)
        self.assertEqual(lifecycle.snapshot().nodes["a"]["status"], "cancelled")
        self.assertEqual(lifecycle.finalize_execution(), "cancelled")

    def test_invalid_outcome_is_rejected_without_events_or_state_change(self) -> None:
        lifecycle = self.active({"a": True})
        lifecycle.mark_node_ready("a")
        lifecycle.start_attempt("a", "a-1")
        before = lifecycle.snapshot()
        event_count = len(lifecycle.event_sink.events())
        with self.assertRaises(ValueError):
            lifecycle.finish_attempt("a-1", "bogus")  # type: ignore[arg-type]
        self.assertEqual(lifecycle.snapshot().attempts["a-1"]["status"], before.attempts["a-1"]["status"])
        self.assertEqual(len(lifecycle.event_sink.events()), event_count)

    def test_quiescence_and_optional_aggregation(self) -> None:
        lifecycle = self.active()
        self.ready(lifecycle)
        lifecycle.start_attempt("required", "a-1")
        with self.assertRaises(InvalidTransition):
            lifecycle.finalize_execution()
        self.publish(lifecycle, "a-1")
        lifecycle.finish_attempt("a-1", "succeeded")
        lifecycle.mark_node_ready("optional")
        lifecycle.start_attempt("optional", "b-1")
        lifecycle.finish_attempt("b-1", "failed")
        self.assertEqual(lifecycle.finalize_execution(), "succeeded")
        self.assertTrue(lifecycle.snapshot().degraded)

    def test_events_are_monotonic_scoped_and_failed_commands_emit_nothing(self) -> None:
        lifecycle = self.active({"a": True})
        event_count = len(lifecycle.event_sink.events())
        with self.assertRaises(InvalidTransition):
            lifecycle.start_attempt("a", "a-1")
        self.assertEqual(len(lifecycle.event_sink.events()), event_count)
        lifecycle.mark_node_ready("a")

        threads = [threading.Thread(target=lambda: lifecycle.request_cancel("a")) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        events = lifecycle.event_sink.events()
        self.assertEqual([event["sequence"] for event in events], list(range(len(events))))
        self.assertTrue(all(event["run_id"] == "run-1" for event in events))
        for event in events:
            if event["scope"] == "project":
                self.assertIsNone(event["analysis_id"])
            if event["scope"] == "analysis":
                self.assertEqual(event["analysis_id"], "a")
                self.assertIsNone(event["attempt_id"])

    def test_snapshot_is_not_mutable(self) -> None:
        lifecycle = self.active({"a": True})
        snapshot = lifecycle.snapshot()
        with self.assertRaises(TypeError):
            snapshot.nodes["a"]["status"] = "failed"
        with self.assertRaises(TypeError):
            snapshot.nodes["new"] = {}

    def test_node_spec_invariants_and_token_are_strict(self) -> None:
        with self.assertRaises(ValueError):
            InMemoryLifecycle("run-1", {"a": {"required": True, "effective_required": False}})
        with self.assertRaises(ValueError):
            InMemoryLifecycle("run-1", {"a": {"required": "yes"}})
        with self.assertRaises(ValueError):
            InMemoryLifecycle("run-1", {"a": False})

        lifecycle = self.active({"a": True})
        lifecycle.mark_node_ready("a")
        token = lifecycle.start_attempt("a", "a-1")
        self.assertFalse(hasattr(token, "request"))
        self.assertEqual(lifecycle.request_cancel("a"), "accepted")
        snapshot = lifecycle.snapshot()
        self.assertTrue(snapshot.nodes["a"]["cancel_requested"])
        self.assertTrue(snapshot.attempts["a-1"]["cancel_requested"])

    def test_event_identity_and_emit_failures_do_not_split_state(self) -> None:
        foreign_sink = InMemoryEventSink("other-run", clock=lambda: 0.0)
        with self.assertRaises(ValueError):
            InMemoryLifecycle("run-1", {"a": True}, event_sink=foreign_sink)

        calls = 0

        def failing_clock() -> float:
            nonlocal calls
            calls += 1
            if calls > 1:
                raise RuntimeError("event clock unavailable")
            return 0.0

        lifecycle = InMemoryLifecycle("run-1", {"a": True}, clock=failing_clock)
        with self.assertRaises(RuntimeError):
            lifecycle.start_resolving()
        self.assertEqual(lifecycle.snapshot().execution_status, "queued")

    def test_resolving_cancel_cannot_be_overwritten(self) -> None:
        lifecycle = InMemoryLifecycle("run-1", {"a": True})
        lifecycle.start_resolving()
        lifecycle.request_cancel()
        with self.assertRaises(InvalidTransition):
            lifecycle.activate_execution()
        lifecycle.fail_resolution()
        self.assertEqual(lifecycle.snapshot().execution_status, "cancelled")

        required = InMemoryLifecycle("run-1", {"a": True})
        required.start_resolving()
        required.request_cancel("a")
        required.fail_resolution()
        self.assertEqual(required.snapshot().execution_status, "cancelled")

        optional = InMemoryLifecycle("run-1", {"a": False, "b": True})
        optional.start_resolving()
        optional.request_cancel("a")
        optional.fail_resolution()
        self.assertEqual(optional.snapshot().execution_status, "failed")

    def test_late_failure_does_not_partially_commit_when_event_emission_fails(self) -> None:
        calls = 0

        def flaky_clock() -> float:
            nonlocal calls
            calls += 1
            if calls == 7:
                raise RuntimeError("event clock unavailable")
            return 0.0

        lifecycle = InMemoryLifecycle("run-1", {"a": True}, clock=flaky_clock)
        lifecycle.start_resolving()
        lifecycle.activate_execution()
        lifecycle.mark_node_ready("a")
        lifecycle.start_attempt("a", "a-1")
        lifecycle.request_cancel("a")
        with self.assertRaises(RuntimeError):
            lifecycle.finish_attempt("a-1", "failed")
        attempt = lifecycle.snapshot().attempts["a-1"]
        self.assertEqual(attempt["status"], "queued")
        self.assertNotIn("late_backend_outcome", attempt)


if __name__ == "__main__":
    unittest.main()
