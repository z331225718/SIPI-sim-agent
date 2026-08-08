"""PyBERT strict link adapters (M2-02)."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

from sipi_contracts import (
    BackendExecutionRequestV1,
    parse_channel_resolution_policy,
    parse_network_tensor,
)

from .process import (
    BackendOutcome,
    CommandBuilder,
    ProcessResult,
    assemble_backend_result,
    invocation,
    platform_error,
)
from .capabilities import AdapterCapability
from .channel_resolver import ChannelResolutionError, resolve_channel
from .spi import AdapterContractError, UnsupportedCapabilityError


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact_ref(
    *,
    relative_path: str,
    content_schema: str,
    mime_type: str,
    path: Path,
    producer: str,
    role: str,
) -> dict[str, Any]:
    return {
        "schema": "sipi.artifact-ref.v1",
        "content_schema": content_schema,
        "relative_path": relative_path,
        "mime_type": mime_type,
        "sha256": _sha256(path),
        "byte_length": path.stat().st_size,
        "producer": producer,
        "role": role,
        "extensions": {},
    }


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _finite_positive(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise AdapterContractError(f"{field} must be a finite positive number")
    return float(value)


def _finite_samples(value: Any) -> list[float]:
    if not isinstance(value, list) or not value:
        raise AdapterContractError("external_resolution.impulse_response_volts_per_second must be a non-empty array")
    if any(isinstance(sample, bool) or not isinstance(sample, (int, float)) or not math.isfinite(sample) for sample in value):
        raise AdapterContractError("external_resolution.impulse_response_volts_per_second must contain finite numbers")
    return [float(sample) for sample in value]


class PyBertNativeAdapter(CommandBuilder):
    """link.simulate.v1 over the strict PyBERT ``sim-native`` CLI.

    The payload carries an inline SimulationInputV1 document; the engine writes
    ``meta.json`` (schema ``pybert.native-cli-result.v1``) and ``arrays.npz``
    into the output directory, which are handed to the runtime artifact store.
    This adapter never calls PyBERT's auto/compare entry points.
    """

    domain_result_schema = "pybert.native-cli-result.v1"

    @classmethod
    def capability_entries(cls) -> tuple[AdapterCapability, ...]:
        return (
            AdapterCapability(
                operation="link.simulate.v1",
                payload_schema="pybert.simulation.v1",
                domain_result_schemas=("pybert.native-cli-result.v1", "pybert.arrays.v1"),
                behavior_profile="default",
                role="candidate",
                execution_mode="process",
            ),
        )

    @classmethod
    def capabilities(cls, engine_instance_id: str, bundle_hash: str):
        from .capabilities import build_engine_capabilities

        return build_engine_capabilities(engine_instance_id=engine_instance_id, bundle_hash=bundle_hash, entries=cls.capability_entries())

    def build(self, request: BackendExecutionRequestV1, bundle_path: Path, workdir: Path) -> list[str]:
        wire = request.to_wire()
        if wire.get("payload_artifact") is not None:
            raise UnsupportedCapabilityError("payload_artifact handoff is a later M2 slice")
        payload = wire["payload"]
        simulation_input = payload.get("simulation_input")
        if not isinstance(simulation_input, Mapping):
            raise AdapterContractError("payload requires an inline simulation_input object")
        input_path = workdir / "input.json"
        input_path.write_text(json.dumps(simulation_input, sort_keys=True), encoding="utf-8")
        return [
            *invocation(bundle_path),
            "sim-native",
            str(input_path),
            "--output-dir",
            str(workdir / "out"),
        ]

    def build_outcome(self, request: BackendExecutionRequestV1, engine_entry: Mapping[str, Any], workdir: Path, process: ProcessResult) -> BackendOutcome:
        out_root = workdir / "out"
        meta_path = out_root / "meta.json"
        arrays_path = out_root / "arrays.npz"
        if not meta_path.is_file():
            return BackendOutcome(
                assemble_backend_result(
                    request,
                    status="failed",
                    error=platform_error("ExternalModelFailure", "engine succeeded but produced no meta.json"),
                )
            )
        meta: Any = json.loads(meta_path.read_text(encoding="utf-8"))
        artifacts = [
            _artifact_ref(
                relative_path="out/meta.json",
                content_schema=self.domain_result_schema,
                mime_type="application/json",
                path=meta_path,
                producer=request["engine_instance_id"],
                role="domain_result",
            )
        ]
        if arrays_path.is_file():
            artifacts.append(
                _artifact_ref(
                    relative_path="out/arrays.npz",
                    content_schema="pybert.arrays.v1",
                    mime_type="application/octet-stream",
                    path=arrays_path,
                    producer=request["engine_instance_id"],
                    role="data",
                )
            )
        return BackendOutcome(
            assemble_backend_result(
                request,
                status="succeeded",
                domain_result=meta,
                domain_result_schema=self.domain_result_schema,
                artifacts=tuple(artifacts),
            ),
            artifact_paths=(meta_path, arrays_path) if arrays_path.is_file() else (meta_path,),
        )


class PyBertResolvedChannelAdapter(CommandBuilder):
    """Inject one externally resolved S2P/S4P impulse through the M4 resolver.

    This boundary does not calculate an S-parameter transform.  The Python
    external producer supplies a frozen, pre-policy-sign voltage-transfer
    impulse and binds it to the parsed network and policy hashes.  The adapter
    then calls the sole production resolver exactly once before the existing
    ``sim-native`` CLI consumes its ``ChannelResponseV1`` output.
    """

    domain_result_schema = "pybert.native-cli-result.v1"
    request_schema = "sipi.pybert-resolved-channel-request.v1"
    _sentinel = {"kind": "external_model", "value": {"kind": "sipi_resolved_channel", "capability": "adapter_injected_v1"}}

    @classmethod
    def capability_entries(cls) -> tuple[AdapterCapability, ...]:
        return (
            AdapterCapability(
                operation="link.simulate.v1",
                payload_schema=cls.request_schema,
                domain_result_schemas=(cls.domain_result_schema, "pybert.arrays.v1"),
                behavior_profile="m4-resolved-channel",
                role="candidate",
                execution_mode="process",
            ),
        )

    @classmethod
    def capabilities(cls, engine_instance_id: str, bundle_hash: str):
        from .capabilities import build_engine_capabilities

        return build_engine_capabilities(engine_instance_id=engine_instance_id, bundle_hash=bundle_hash, entries=cls.capability_entries())

    def build(self, request: BackendExecutionRequestV1, bundle_path: Path, workdir: Path) -> list[str]:
        simulation_input, provenance = self._resolve_payload(request)
        (workdir / "input.json").write_text(json.dumps(simulation_input, sort_keys=True), encoding="utf-8")
        (workdir / "resolved-channel-provenance.json").write_text(
            json.dumps(provenance, sort_keys=True), encoding="utf-8"
        )
        return [
            *invocation(bundle_path),
            "sim-native",
            str(workdir / "input.json"),
            "--output-dir",
            str(workdir / "out"),
        ]

    def _resolve_payload(self, request: BackendExecutionRequestV1) -> tuple[dict[str, Any], dict[str, Any]]:
        wire = request.to_wire()
        if wire.get("payload_artifact") is not None:
            raise UnsupportedCapabilityError("resolved-channel payload_artifact handoff is unsupported")
        if wire["payload_schema"] != self.request_schema:
            raise UnsupportedCapabilityError(f"resolved-channel handoff requires payload schema {self.request_schema}")
        payload = wire["payload"]
        if not isinstance(payload, Mapping) or payload.get("schema") != self.request_schema:
            raise AdapterContractError(f"payload must be a {self.request_schema} object")
        if set(payload) != {"schema", "simulation_input", "network", "resolution_policy", "external_resolution"}:
            raise AdapterContractError("resolved-channel payload contains unsupported or missing fields")

        simulation_input = payload["simulation_input"]
        if not isinstance(simulation_input, Mapping) or simulation_input.get("schema") != "pybert.simulation.v1":
            raise AdapterContractError("simulation_input must be a pybert.simulation.v1 object")
        channel = simulation_input.get("channel")
        if channel != self._sentinel:
            raise AdapterContractError("simulation_input.channel must be the sipi_resolved_channel injection sentinel")
        timebase = simulation_input.get("timebase")
        if not isinstance(timebase, Mapping):
            raise AdapterContractError("simulation_input.timebase is required for resolved-channel injection")

        try:
            network = parse_network_tensor(payload["network"])
            policy = parse_channel_resolution_policy(payload["resolution_policy"])
        except Exception as error:
            raise AdapterContractError(f"invalid network or resolution_policy: {error}") from error
        external = payload["external_resolution"]
        if not isinstance(external, Mapping):
            raise AdapterContractError("external_resolution must be an object")
        self._validate_external_resolution(network.to_wire(), policy.to_wire(), external, timebase)
        impulse = _finite_samples(external["impulse_response_volts_per_second"])
        try:
            resolved_channel, report = resolve_channel(
                network,
                policy,
                impulse_response_volts_per_second=impulse,
                source_impedance=_finite_positive(external["source_impedance_ohm"], "external_resolution.source_impedance_ohm"),
                load_impedance=_finite_positive(external["load_impedance_ohm"], "external_resolution.load_impedance_ohm"),
                sample_interval_s=_finite_positive(external["sample_interval_s"], "external_resolution.sample_interval_s"),
            )
        except ChannelResolutionError as error:
            if error.category == "UnsupportedCapability":
                raise UnsupportedCapabilityError(str(error)) from error
            raise AdapterContractError(str(error)) from error

        resolved_input = dict(simulation_input)
        resolved_input["channel"] = {"kind": "impulse_response", "value": resolved_channel}
        provenance = {
            "schema": "sipi.pybert-resolved-channel-provenance.v1",
            "external_resolution": dict(external),
            "channel_resolution_report": report.to_wire(),
            "resolved_simulation_input_hash": _canonical_sha256(resolved_input),
        }
        return resolved_input, provenance

    @staticmethod
    def _validate_external_resolution(
        network: Mapping[str, Any],
        policy: Mapping[str, Any],
        external: Mapping[str, Any],
        timebase: Mapping[str, Any],
    ) -> None:
        required = {
            "impulse_response_volts_per_second",
            "sample_interval_s",
            "source_impedance_ohm",
            "load_impedance_ohm",
            "source_network_hash",
            "policy_hash",
            "impulse_hash",
            "producer",
            "semantics",
            "port_intent",
            "source_discrete_impulse_hash",
            "source_units",
            "unit_conversion",
            "source_channel_file_sha256",
            "legacy_channel_config_hash",
        }
        if set(external) != required:
            raise AdapterContractError("external_resolution contains unsupported or missing fields")
        impulse = _finite_samples(external["impulse_response_volts_per_second"])
        _finite_positive(external["sample_interval_s"], "external_resolution.sample_interval_s")
        _finite_positive(external["source_impedance_ohm"], "external_resolution.source_impedance_ohm")
        _finite_positive(external["load_impedance_ohm"], "external_resolution.load_impedance_ohm")
        hashes = {
            "source_network_hash": _canonical_sha256(network),
            "policy_hash": _canonical_sha256(policy),
            "impulse_hash": _canonical_sha256(impulse),
        }
        for field, expected in hashes.items():
            if external[field] != expected:
                raise AdapterContractError(f"external_resolution.{field} does not match its canonical input")
        native_sample_interval = _finite_positive(timebase.get("sampleInterval"), "simulation_input.timebase.sampleInterval")
        if external["sample_interval_s"] != native_sample_interval:
            raise AdapterContractError("external_resolution.sample_interval_s must equal simulation_input.timebase.sampleInterval")
        for field in (
            "source_discrete_impulse_hash",
            "source_channel_file_sha256",
            "legacy_channel_config_hash",
        ):
            value = external[field]
            if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise AdapterContractError(f"external_resolution.{field} must be a lowercase SHA-256 hex digest")
        if external["source_units"] != "V/sample" or external["unit_conversion"] != "discrete_v_per_sample_to_v_per_s":
            raise AdapterContractError("external_resolution must declare the discrete V/sample to V/s conversion")
        producer = external["producer"]
        if not isinstance(producer, Mapping) or set(producer) != {"tool", "package", "version", "build_id"} or any(
            not isinstance(value, str) or not value.strip() for value in producer.values()
        ):
            raise AdapterContractError("external_resolution.producer requires non-empty tool/package/version/build_id")
        if external["semantics"] != {
            "transfer_kind": "voltage_transfer",
            "impulse_units": "V/s",
            "policy_sign_applied": False,
        }:
            raise AdapterContractError("external_resolution.semantics must declare pre-policy-sign voltage-transfer V/s")
        selected = [item["port_id"] for item in policy["port_selection"]]
        declared_ports = {item["id"] for item in network["port_map"]["ports"]}
        if not set(selected).issubset(declared_ports):
            raise AdapterContractError("resolution_policy.port_selection references a network port that is not declared")
        if policy["output"].get("signal_intent") != "voltage" or policy["output"].get("current_to_voltage_sign") != 1:
            raise UnsupportedCapabilityError("resolved-channel handoff requires voltage output with current_to_voltage_sign=1")
        expected_intent = {
            "selected_port_ids": selected,
            "termination": policy["termination"],
            "reference_port": policy["output"].get("reference_port"),
            "wave_definition": network["wave_definition"],
            "z0": network["z0"],
        }
        if external["port_intent"] != expected_intent:
            raise AdapterContractError("external_resolution.port_intent does not match network and resolution_policy")
        normalization = policy["normalization"]
        if normalization["fft"] != "none":
            raise UnsupportedCapabilityError("resolved-channel handoff requires normalization.fft=none")

    def build_outcome(
        self,
        request: BackendExecutionRequestV1,
        engine_entry: Mapping[str, Any],
        workdir: Path,
        process: ProcessResult,
    ) -> BackendOutcome:
        out_root = workdir / "out"
        meta_path = out_root / "meta.json"
        arrays_path = out_root / "arrays.npz"
        provenance_path = workdir / "resolved-channel-provenance.json"
        if not meta_path.is_file() or not provenance_path.is_file():
            return BackendOutcome(
                assemble_backend_result(
                    request,
                    status="failed",
                    error=platform_error("ExternalModelFailure", "engine succeeded but produced no resolved-channel result"),
                )
            )
        meta: Any = json.loads(meta_path.read_text(encoding="utf-8"))
        if not isinstance(meta, dict) or meta.get("schema") != self.domain_result_schema:
            return BackendOutcome(
                assemble_backend_result(
                    request,
                    status="failed",
                    error=platform_error("ExternalModelFailure", "engine produced an invalid resolved-channel result schema"),
                )
            )
        meta["platform_channel_resolution"] = json.loads(provenance_path.read_text(encoding="utf-8"))
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        artifacts = [
            _artifact_ref(
                relative_path="out/meta.json",
                content_schema=self.domain_result_schema,
                mime_type="application/json",
                path=meta_path,
                producer=request["engine_instance_id"],
                role="domain_result",
            )
        ]
        if arrays_path.is_file():
            artifacts.append(
                _artifact_ref(
                    relative_path="out/arrays.npz",
                    content_schema="pybert.arrays.v1",
                    mime_type="application/octet-stream",
                    path=arrays_path,
                    producer=request["engine_instance_id"],
                    role="data",
                )
            )
        return BackendOutcome(
            assemble_backend_result(
                request,
                status="succeeded",
                domain_result=meta,
                domain_result_schema=self.domain_result_schema,
                artifacts=tuple(artifacts),
            ),
            artifact_paths=(meta_path, arrays_path) if arrays_path.is_file() else (meta_path,),
        )


class PyBertAgentSpiceResponseAdapter(CommandBuilder):
    """Strict current-drive Link execution from an existing RFM artifact pair.

    The paired Agent-Spice artifacts are materialized and hash-verified by the
    platform before this adapter runs.  The PyBERT CLI consumes them directly;
    it does not invoke Agent-Spice or turn its impedance response into a
    voltage-transfer ``ChannelResponseV1``.  S2P/S4P remains owned by the
    M4 production resolver and its explicit Python external boundary.
    """

    domain_result_schema = "pybert.agent-spice-current-driven-link-cli-result.v1"
    request_schema = "pybert.agent-spice-current-driven-link-request.v1"

    @classmethod
    def capability_entries(cls) -> tuple[AdapterCapability, ...]:
        return (
            AdapterCapability(
                operation="link.simulate.v1",
                payload_schema=cls.request_schema,
                domain_result_schemas=(
                    cls.domain_result_schema,
                    "pybert.agent-spice-current-driven-link-arrays.v1",
                ),
                behavior_profile="agent-spice-current-drive",
                role="candidate",
                execution_mode="process",
            ),
        )

    @classmethod
    def capabilities(cls, engine_instance_id: str, bundle_hash: str):
        from .capabilities import build_engine_capabilities

        return build_engine_capabilities(engine_instance_id=engine_instance_id, bundle_hash=bundle_hash, entries=cls.capability_entries())

    def build(self, request: BackendExecutionRequestV1, bundle_path: Path, workdir: Path) -> list[str]:
        wire = request.to_wire()
        if wire["payload_schema"] != self.request_schema:
            raise UnsupportedCapabilityError(
                f"Agent-Spice response handoff requires payload schema {self.request_schema}"
            )
        payload = wire["payload"]
        if not isinstance(payload, Mapping) or payload.get("schema") != self.request_schema:
            raise AdapterContractError(f"payload must be a {self.request_schema} object")
        metadata = self._bound_input(request, "rfm_metadata", "agent-spice.rfm-response.v1")
        response = self._bound_input(request, "rfm_response", "agent-spice.rfm-response-binary.v1")
        input_path = workdir / "current-driven-link.json"
        input_path.write_text(json.dumps(dict(payload), sort_keys=True), encoding="utf-8")
        return [
            *invocation(bundle_path),
            "sim-agent-spice-response",
            str(input_path),
            "--rfm-metadata",
            str(workdir / metadata["relative_path"]),
            "--rfm-response",
            str(workdir / response["relative_path"]),
            "--output-dir",
            str(workdir / "out"),
        ]

    @staticmethod
    def _bound_input(
        request: BackendExecutionRequestV1,
        name: str,
        content_schema: str,
    ) -> Mapping[str, Any]:
        artifact = request["bound_inputs"].get(name)
        if not isinstance(artifact, Mapping) or artifact.get("content_schema") != content_schema:
            raise AdapterContractError(f"bound input {name!r} must have content schema {content_schema}")
        return artifact

    def build_outcome(
        self,
        request: BackendExecutionRequestV1,
        engine_entry: Mapping[str, Any],
        workdir: Path,
        process: ProcessResult,
    ) -> BackendOutcome:
        out_root = workdir / "out"
        meta_path = out_root / "meta.json"
        arrays_path = out_root / "arrays.npz"
        if not meta_path.is_file():
            return BackendOutcome(
                assemble_backend_result(
                    request,
                    status="failed",
                    error=platform_error("ExternalModelFailure", "engine succeeded but produced no current-driven meta.json"),
                )
            )
        meta: Any = json.loads(meta_path.read_text(encoding="utf-8"))
        if not isinstance(meta, dict) or meta.get("schema") != self.domain_result_schema:
            return BackendOutcome(
                assemble_backend_result(
                    request,
                    status="failed",
                    error=platform_error("ExternalModelFailure", "engine produced an invalid current-driven result schema"),
                )
            )
        meta["platform_rfm_artifacts"] = {
            name: {
                key: artifact[key]
                for key in ("relative_path", "content_schema", "sha256", "byte_length", "producer", "role")
            }
            for name, artifact in request["bound_inputs"].items()
            if name in {"rfm_metadata", "rfm_response"}
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        artifacts = [
            _artifact_ref(
                relative_path="out/meta.json",
                content_schema=self.domain_result_schema,
                mime_type="application/json",
                path=meta_path,
                producer=request["engine_instance_id"],
                role="domain_result",
            )
        ]
        if arrays_path.is_file():
            artifacts.append(
                _artifact_ref(
                    relative_path="out/arrays.npz",
                    content_schema="pybert.agent-spice-current-driven-link-arrays.v1",
                    mime_type="application/octet-stream",
                    path=arrays_path,
                    producer=request["engine_instance_id"],
                    role="data",
                )
            )
        return BackendOutcome(
            assemble_backend_result(
                request,
                status="succeeded",
                domain_result=meta,
                domain_result_schema=self.domain_result_schema,
                artifacts=tuple(artifacts),
            ),
            artifact_paths=(meta_path, arrays_path) if arrays_path.is_file() else (meta_path,),
        )


class PyBertLinkAdapter(CommandBuilder):
    """Route strict Link payload schemas to their one matching PyBERT adapter."""

    _builders = {
        "pybert.simulation.v1": PyBertNativeAdapter,
        PyBertResolvedChannelAdapter.request_schema: PyBertResolvedChannelAdapter,
        PyBertAgentSpiceResponseAdapter.request_schema: PyBertAgentSpiceResponseAdapter,
    }

    @classmethod
    def capability_entries(cls) -> tuple[AdapterCapability, ...]:
        return tuple(entry for builder in cls._builders.values() for entry in builder.capability_entries())

    @classmethod
    def capabilities(cls, engine_instance_id: str, bundle_hash: str):
        from .capabilities import build_engine_capabilities

        return build_engine_capabilities(engine_instance_id=engine_instance_id, bundle_hash=bundle_hash, entries=cls.capability_entries())

    @classmethod
    def _builder(cls, request: BackendExecutionRequestV1) -> CommandBuilder:
        builder_type = cls._builders.get(request["payload_schema"])
        if builder_type is None:
            raise UnsupportedCapabilityError(f"PyBERT does not support payload schema {request['payload_schema']}")
        return builder_type()

    def build(self, request: BackendExecutionRequestV1, bundle_path: Path, workdir: Path) -> list[str]:
        return self._builder(request).build(request, bundle_path, workdir)

    def build_outcome(
        self,
        request: BackendExecutionRequestV1,
        engine_entry: Mapping[str, Any],
        workdir: Path,
        process: ProcessResult,
    ) -> BackendOutcome:
        return self._builder(request).build_outcome(request, engine_entry, workdir, process)
