from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol, TYPE_CHECKING
from urllib.parse import urlparse
from urllib.request import url2pathname

from justls.ics.domain.observation.models import utc_now_iso
from justls.ics.domain.observation.sequence import (
    SequenceExecutionSnapshot,
    SequenceExecutionState,
    SequenceRecoveryAction,
    SequenceRecoveryInfo,
    SequenceStepState,
)

if TYPE_CHECKING:
    from justls.ics.kernel.runtime import Runtime


SEQUENCE_STORE_SCHEMA_VERSION = 1


class ObservationSequenceStore(Protocol):
    def load(self) -> SequenceExecutionSnapshot | None:
        ...

    def save(self, snapshot: SequenceExecutionSnapshot) -> SequenceExecutionSnapshot:
        ...


def _snapshot_payload(snapshot: SequenceExecutionSnapshot) -> dict[str, Any]:
    return snapshot.model_dump(
        mode="json",
        exclude={"total_steps", "completed_steps"},
    )


class InMemoryObservationSequenceStore:
    def __init__(self, snapshot: SequenceExecutionSnapshot | None = None) -> None:
        self._payload = _snapshot_payload(snapshot) if snapshot is not None else None

    def load(self) -> SequenceExecutionSnapshot | None:
        if self._payload is None:
            return None
        return SequenceExecutionSnapshot.model_validate(self._payload)

    def save(self, snapshot: SequenceExecutionSnapshot) -> SequenceExecutionSnapshot:
        self._payload = _snapshot_payload(snapshot)
        loaded = self.load()
        assert loaded is not None
        return loaded


class JsonObservationSequenceStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> SequenceExecutionSnapshot | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid observation sequence JSON: {self.path}") from exc
        if not isinstance(payload, Mapping):
            raise ValueError(
                f"Observation sequence JSON must contain an object: {self.path}"
            )
        if payload.get("schema_version") != SEQUENCE_STORE_SCHEMA_VERSION:
            raise ValueError(
                "Unsupported observation sequence store schema: "
                f"{payload.get('schema_version')!r}"
            )
        sequence = payload.get("sequence")
        if not isinstance(sequence, Mapping):
            raise ValueError(
                f"Observation sequence JSON must contain a sequence object: {self.path}"
            )
        sequence_payload = dict(sequence)
        plan = sequence_payload.get("plan")
        if isinstance(plan, Mapping) and "save_requested" not in plan:
            migrated_plan = dict(plan)
            migrated_plan["save_requested"] = sequence_payload.get("frame_reservation") is not None
            sequence_payload["plan"] = migrated_plan
        return SequenceExecutionSnapshot.model_validate(sequence_payload)

    def save(self, snapshot: SequenceExecutionSnapshot) -> SequenceExecutionSnapshot:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SEQUENCE_STORE_SCHEMA_VERSION,
            "saved_at_utc": snapshot.last_persisted_at_utc or utc_now_iso(),
            "sequence": _snapshot_payload(snapshot),
        }
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        tmp_path = self.path.with_name(f"{self.path.name}.tmp")
        tmp_path.write_text(text, encoding="utf-8")
        tmp_path.replace(self.path)
        loaded = self.load()
        assert loaded is not None
        return loaded


def _path_from_local_file_uri(uri: str) -> Path | None:
    parsed = urlparse(uri)
    if parsed.scheme.lower() != "file":
        return None
    raw_path = url2pathname(parsed.path)
    if parsed.netloc and parsed.netloc not in {"", "localhost"}:
        raw_path = f"//{parsed.netloc}{raw_path}"
    return Path(raw_path)


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _completed_product_issues(
    snapshot: SequenceExecutionSnapshot,
    data_root: Path | None,
) -> list[str]:
    issues: list[str] = []
    for result in snapshot.step_results:
        if result.state != SequenceStepState.COMPLETED or not result.exposure_record:
            continue
        record = result.exposure_record
        for key in ("primary_data_product", "quicklook"):
            product = record.get(key)
            if not isinstance(product, Mapping) or not product.get("exists"):
                continue
            uri = product.get("uri")
            if not isinstance(uri, str):
                issues.append(f"step {result.index}: {key} has no URI")
                continue
            path = _path_from_local_file_uri(uri)
            if path is None:
                continue
            if data_root is not None and not _is_inside(path, data_root):
                issues.append(f"step {result.index}: {key} is outside data root")
                continue
            try:
                if not path.is_file():
                    issues.append(f"step {result.index}: missing {key} file {path}")
                    continue
                expected = product.get("checksum")
                if key == "primary_data_product" and expected and _checksum(path) != expected:
                    issues.append(f"step {result.index}: FITS checksum mismatch {path}")
            except OSError as exc:
                issues.append(f"step {result.index}: cannot inspect {key} file {path}: {exc}")
    return issues


def _detected_active_files(
    snapshot: SequenceExecutionSnapshot,
    data_root: Path | None,
) -> list[str]:
    active_step = snapshot.active_step
    if data_root is None or active_step is None or not active_step.exp_id:
        return []
    if not data_root.is_dir():
        return []
    token = active_step.exp_id
    matches = [
        path
        for path in data_root.rglob(f"{token}-*")
        if path.is_file() and path.suffix.lower() in {".fits", ".png"}
    ]
    return sorted(str(path.resolve()) for path in matches)


def reconcile_restored_sequence(
    snapshot: SequenceExecutionSnapshot,
    *,
    data_root: str | Path | None,
) -> SequenceExecutionSnapshot:
    """Fail closed when restart leaves detector or data-product outcome uncertain."""

    root = Path(data_root).resolve() if data_root is not None else None
    previous_state = snapshot.state.value
    snapshot.restored_at_utc = utc_now_iso()

    if snapshot.state in {
        SequenceExecutionState.ABORTED,
        SequenceExecutionState.FAILED,
    }:
        return snapshot

    product_issues = _completed_product_issues(snapshot, root)
    if product_issues:
        snapshot.state = SequenceExecutionState.RECOVERY_REQUIRED
        snapshot.active_exposure = False
        snapshot.recovery = SequenceRecoveryInfo(
            reason="completed_data_product_mismatch",
            interrupted_state=previous_state,
            interrupted_index=snapshot.current_index,
            file_issues=product_issues,
            retry_allowed=False,
            allowed_actions=[
                SequenceRecoveryAction.ABORT,
                SequenceRecoveryAction.MARK_FAILED,
            ],
        )
        snapshot.message = (
            "Recovery required: a completed step no longer matches its durable "
            "data-product record. Do not retry automatically."
        )
        snapshot.updated_at_utc = utc_now_iso()
        return snapshot

    if snapshot.active_exposure or snapshot.active_step is not None:
        detected = _detected_active_files(snapshot, root)
        fits_detected = any(Path(path).suffix.lower() == ".fits" for path in detected)
        snapshot.state = SequenceExecutionState.RECOVERY_REQUIRED
        snapshot.active_exposure = False
        snapshot.recovery = SequenceRecoveryInfo(
            reason="interrupted_active_step",
            interrupted_state=previous_state,
            interrupted_index=(
                snapshot.active_step.index
                if snapshot.active_step is not None
                else snapshot.current_index
            ),
            detected_files=detected,
            retry_allowed=not fits_detected,
            allowed_actions=(
                [
                    SequenceRecoveryAction.RETRY_CURRENT_STEP,
                    SequenceRecoveryAction.ABORT,
                    SequenceRecoveryAction.MARK_FAILED,
                ]
                if not fits_detected
                else [
                    SequenceRecoveryAction.ABORT,
                    SequenceRecoveryAction.MARK_FAILED,
                ]
            ),
        )
        snapshot.message = (
            "Recovery required: the process restarted during an active sequence "
            "step. Review detected files before choosing an explicit action."
        )
        snapshot.updated_at_utc = utc_now_iso()
    return snapshot


def initialize_runtime_sequence(
    runtime: Runtime,
    store: ObservationSequenceStore,
    *,
    persistence_path: str | None = None,
) -> None:
    with runtime.sequence_lock:
        if runtime.sequence_execution_loaded:
            return
        runtime.sequence_execution_loaded = True
        runtime.sequence_persistence_path = persistence_path
        try:
            snapshot = store.load()
            if snapshot is not None:
                snapshot = reconcile_restored_sequence(
                    snapshot,
                    data_root=runtime.data_root,
                )
                snapshot.last_persisted_at_utc = utc_now_iso()
                store.save(snapshot)
            runtime.sequence_execution = snapshot
            runtime.sequence_persistence_error = None
        except (OSError, ValueError) as exc:
            runtime.sequence_execution = None
            runtime.sequence_persistence_error = str(exc)
