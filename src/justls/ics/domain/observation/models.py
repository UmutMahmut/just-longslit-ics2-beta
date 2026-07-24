from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def new_obs_id() -> str:
    return f"obs-{uuid4().hex[:12]}"


def new_exp_id() -> str:
    return f"exp-{uuid4().hex[:12]}"


def new_record_id() -> str:
    return f"rec-{uuid4().hex[:12]}"


def new_frame_id() -> str:
    return f"frame-rec-{uuid4().hex[:12]}"


def new_product_id() -> str:
    return f"dp-{uuid4().hex[:12]}"


@dataclass(slots=True)
class FrameResult:
    frame_token: str | None
    file_uri: str | None
    kept: bool
    early_stop: bool
    discarded: bool
    checksum: str | None
    started_at_utc: str | None
    finished_at_utc: str | None
    result: str
    quicklook_uri: str | None = None
    exists: bool = False
    simulated: bool = True
    physical_camera_id: str | None = None
    logical_channels: tuple[str, ...] = ()
    shared_capture_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_token": self.frame_token,
            "file_uri": self.file_uri,
            "kept": self.kept,
            "early_stop": self.early_stop,
            "discarded": self.discarded,
            "checksum": self.checksum,
            "started_at_utc": self.started_at_utc,
            "finished_at_utc": self.finished_at_utc,
            "result": self.result,
            "quicklook_uri": self.quicklook_uri,
            "exists": self.exists,
            "simulated": self.simulated,
            "physical_camera_id": self.physical_camera_id,
            "logical_channels": list(self.logical_channels),
            "shared_capture_id": self.shared_capture_id,
        }


class DataProductKind(str, Enum):
    FITS = "fits"
    QUICKLOOK = "quicklook"


class DataProductState(str, Enum):
    NOT_CREATED = "not_created"
    SIMULATED_REFERENCE = "simulated_reference"
    AVAILABLE = "available"
    FAILED = "failed"


class QualityFlag(str, Enum):
    UNKNOWN = "unknown"
    SIMULATED = "simulated"
    DISCARDED = "discarded"
    NO_FITS_WRITER = "no_fits_writer"
    EARLY_STOP = "early_stop"


class DataProductRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str = Field(default_factory=new_product_id)
    kind: DataProductKind
    state: DataProductState
    uri: str | None = None
    exists: bool = False
    simulated: bool = False
    media_type: str | None = None
    checksum: str | None = None
    created_at_utc: str | None = None
    message: str | None = None

    @classmethod
    def available_file(
        cls,
        *,
        kind: DataProductKind,
        uri: str,
        media_type: str,
        checksum: str | None = None,
        simulated: bool = False,
    ) -> "DataProductRef":
        return cls(
            kind=kind,
            state=DataProductState.AVAILABLE,
            uri=uri,
            exists=True,
            simulated=simulated,
            media_type=media_type,
            checksum=checksum,
            created_at_utc=utc_now_iso(),
            message=(
                "File written by the simulated camera pipeline."
                if simulated
                else "File written by the camera pipeline."
            ),
        )

    @classmethod
    def simulated_fits(
        cls,
        *,
        obs_id: str,
        exp_id: str,
        frame_token: str | None,
        checksum: str | None = None,
    ) -> "DataProductRef":
        token = frame_token or "frame"
        return cls(
            kind=DataProductKind.FITS,
            state=DataProductState.SIMULATED_REFERENCE,
            uri=f"sim://justls/{obs_id}/{exp_id}/{token}.fits",
            exists=False,
            simulated=True,
            media_type="application/fits",
            checksum=checksum,
            created_at_utc=utc_now_iso(),
            message="Simulator reference only; no FITS file has been written.",
        )

    @classmethod
    def simulated_quicklook(
        cls,
        *,
        obs_id: str,
        exp_id: str,
        frame_token: str | None,
    ) -> "DataProductRef":
        token = frame_token or "frame"
        return cls(
            kind=DataProductKind.QUICKLOOK,
            state=DataProductState.SIMULATED_REFERENCE,
            uri=f"sim://justls/{obs_id}/{exp_id}/{token}-quicklook.png",
            exists=False,
            simulated=True,
            media_type="image/png",
            created_at_utc=utc_now_iso(),
            message="Simulator quicklook reference only; no image file has been written.",
        )

    @classmethod
    def not_created(
        cls,
        *,
        kind: DataProductKind,
        message: str,
    ) -> "DataProductRef":
        return cls(
            kind=kind,
            state=DataProductState.NOT_CREATED,
            exists=False,
            simulated=False,
            created_at_utc=utc_now_iso(),
            message=message,
        )


class FitsHeaderSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    obs_id: str
    exp_id: str
    frame_type: str
    exp_time_s: float
    detector_profile: str | None = None
    setup_file_stem: str | None = None
    cards: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_observation_meta(
        cls,
        observation_meta: Any,
        frame_result: FrameResult | None = None,
    ) -> "FitsHeaderSummary":
        detector_config = observation_meta.detector_config or {}
        setup_context = observation_meta.setup_context or {}
        detector_profile = (
            detector_config.get("profile_name")
            if isinstance(detector_config, dict)
            else None
        )
        setup_file_stem = (
            setup_context.get("file_stem")
            if isinstance(setup_context, dict)
            else None
        )
        simulated = frame_result.simulated if frame_result is not None else True
        cards: dict[str, Any] = {
            "OBS_ID": observation_meta.obs_id,
            "EXP_ID": observation_meta.exp_id,
            "FRAMETYP": observation_meta.frame_type,
            "EXPTIME": observation_meta.exp_time_s,
            "SIMULATE": simulated,
        }
        if frame_result is not None:
            cards.update(
                {
                    "CAMERA": frame_result.physical_camera_id,
                    "SHARED": bool(frame_result.shared_capture_id),
                    "CHANNELS": ",".join(frame_result.logical_channels),
                }
            )
        return cls(
            obs_id=observation_meta.obs_id,
            exp_id=observation_meta.exp_id,
            frame_type=observation_meta.frame_type,
            exp_time_s=observation_meta.exp_time_s,
            detector_profile=detector_profile,
            setup_file_stem=setup_file_stem,
            cards=cards,
        )


class FrameRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frame_id: str = Field(default_factory=new_frame_id)
    obs_id: str
    exp_id: str
    frame_type: str
    exp_time_s: float
    state: str
    frame_token: str | None = None
    kept: bool
    early_stop: bool
    discarded: bool
    started_at_utc: str | None = None
    finished_at_utc: str | None = None
    data_product: DataProductRef
    quicklook: DataProductRef | None = None
    fits_header: FitsHeaderSummary | None = None
    quality_flags: list[QualityFlag] = Field(default_factory=list)
    physical_camera_id: str | None = None
    logical_channels: list[str] = Field(default_factory=list)
    shared_capture_id: str | None = None


class ExposureRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(default_factory=new_record_id)
    obs_id: str
    exp_id: str
    state: str
    frame_type: str
    exp_time_s: float
    created_at_utc: str
    started_at_utc: str | None = None
    finished_at_utc: str | None = None
    data_product_state: DataProductState
    frames: list[FrameRecord] = Field(default_factory=list)
    primary_data_product: DataProductRef | None = None
    quicklook: DataProductRef | None = None
    fits_header: FitsHeaderSummary | None = None
    quality_flags: list[QualityFlag] = Field(default_factory=list)
    simulated: bool = True
    message: str | None = None
    physical_camera_id: str | None = None
    logical_channels: list[str] = Field(default_factory=list)
    shared_capture_id: str | None = None

    @classmethod
    def from_frame_result(
        cls,
        *,
        observation_meta: Any,
        frame_result: FrameResult,
    ) -> "ExposureRecord":
        discarded = frame_result.discarded or not frame_result.kept
        fits_header = FitsHeaderSummary.from_observation_meta(
            observation_meta,
            frame_result,
        )

        flags: list[QualityFlag] = []
        if frame_result.simulated:
            flags.append(QualityFlag.SIMULATED)
        if frame_result.early_stop:
            flags.append(QualityFlag.EARLY_STOP)
        if discarded:
            flags.append(QualityFlag.DISCARDED)
        else:
            flags.append(QualityFlag.NO_FITS_WRITER)

        if discarded:
            data_product = DataProductRef.not_created(
                kind=DataProductKind.FITS,
                message="Exposure was discarded; no data product was created.",
            )
            quicklook = None
            state = "discarded"
            message = "Exposure discarded; data product intentionally absent."
        elif frame_result.file_uri and frame_result.exists:
            data_product = DataProductRef.available_file(
                kind=DataProductKind.FITS,
                uri=frame_result.file_uri,
                media_type="application/fits",
                checksum=frame_result.checksum,
                simulated=frame_result.simulated,
            )
            quicklook = (
                DataProductRef.available_file(
                    kind=DataProductKind.QUICKLOOK,
                    uri=frame_result.quicklook_uri,
                    media_type="image/png",
                    simulated=frame_result.simulated,
                )
                if frame_result.quicklook_uri
                else None
            )
            state = "completed"
            message = "Exposure completed and local data products were written."
        else:
            flags.append(QualityFlag.NO_FITS_WRITER)
            data_product = DataProductRef.simulated_fits(
                obs_id=observation_meta.obs_id,
                exp_id=observation_meta.exp_id,
                frame_token=frame_result.frame_token,
                checksum=frame_result.checksum,
            )
            quicklook = DataProductRef.simulated_quicklook(
                obs_id=observation_meta.obs_id,
                exp_id=observation_meta.exp_id,
                frame_token=frame_result.frame_token,
            )
            state = "completed"
            message = (
                "Exposure completed in simulator; data products are references "
                "only until a real writer exists."
            )

        frame = FrameRecord(
            obs_id=observation_meta.obs_id,
            exp_id=observation_meta.exp_id,
            frame_type=observation_meta.frame_type,
            exp_time_s=observation_meta.exp_time_s,
            state=state,
            frame_token=frame_result.frame_token,
            kept=frame_result.kept,
            early_stop=frame_result.early_stop,
            discarded=frame_result.discarded,
            started_at_utc=frame_result.started_at_utc,
            finished_at_utc=frame_result.finished_at_utc,
            data_product=data_product,
            quicklook=quicklook,
            fits_header=fits_header,
            quality_flags=flags,
            physical_camera_id=frame_result.physical_camera_id,
            logical_channels=list(frame_result.logical_channels),
            shared_capture_id=frame_result.shared_capture_id,
        )

        return cls(
            obs_id=observation_meta.obs_id,
            exp_id=observation_meta.exp_id,
            state=state,
            frame_type=observation_meta.frame_type,
            exp_time_s=observation_meta.exp_time_s,
            created_at_utc=observation_meta.created_at_utc,
            started_at_utc=observation_meta.started_at_utc,
            finished_at_utc=observation_meta.finished_at_utc,
            data_product_state=data_product.state,
            frames=[frame],
            primary_data_product=data_product,
            quicklook=quicklook,
            fits_header=fits_header,
            quality_flags=flags,
            simulated=frame_result.simulated,
            message=message,
            physical_camera_id=frame_result.physical_camera_id,
            logical_channels=list(frame_result.logical_channels),
            shared_capture_id=frame_result.shared_capture_id,
        )


@dataclass(slots=True)
class ObservationMeta:
    obs_id: str
    exp_id: str
    frame_type: str
    exp_time_s: float
    state: str
    created_at_utc: str
    started_at_utc: str | None = None
    finished_at_utc: str | None = None
    operator_note: str | None = None
    instrument_snapshot: dict[str, Any] | None = None
    calibration_snapshot: dict[str, Any] | None = None
    detector_config: dict[str, Any] | None = None
    preset_apply: dict[str, Any] | None = None
    setup_context: dict[str, Any] | None = None
    data_preview: dict[str, Any] | None = None
    frame_results: list[dict[str, Any]] = field(default_factory=list)
    data_products: list[dict[str, Any]] = field(default_factory=list)
    quicklooks: list[dict[str, Any]] = field(default_factory=list)
    fits_header_summary: dict[str, Any] | None = None
    exposure_record: dict[str, Any] | None = None

    @classmethod
    def create(
        cls,
        *,
        frame_type: str,
        exp_time_s: float,
        operator_note: str | None = None,
        instrument_snapshot: dict[str, Any] | None = None,
        calibration_snapshot: dict[str, Any] | None = None,
        detector_config: dict[str, Any] | None = None,
        preset_apply: dict[str, Any] | None = None,
        setup_context: dict[str, Any] | None = None,
        data_preview: dict[str, Any] | None = None,
    ) -> "ObservationMeta":
        return cls(
            obs_id=new_obs_id(),
            exp_id=new_exp_id(),
            frame_type=frame_type,
            exp_time_s=float(exp_time_s),
            state="armed",
            created_at_utc=utc_now_iso(),
            operator_note=operator_note,
            instrument_snapshot=instrument_snapshot,
            calibration_snapshot=calibration_snapshot,
            detector_config=detector_config,
            preset_apply=preset_apply,
            setup_context=setup_context,
            data_preview=data_preview,
        )

    def mark_exposing(self) -> None:
        self.state = "exposing"
        if self.started_at_utc is None:
            self.started_at_utc = utc_now_iso()

    def mark_completed(self, *, finished_at_utc: str | None = None) -> None:
        self.state = "completed"
        self.finished_at_utc = finished_at_utc or utc_now_iso()

    def mark_discarded(self, *, finished_at_utc: str | None = None) -> None:
        self.state = "discarded"
        self.finished_at_utc = finished_at_utc or utc_now_iso()

    def add_frame_result(self, frame_result: FrameResult) -> None:
        self.frame_results.append(frame_result.to_dict())

    def attach_exposure_record(self, exposure_record: ExposureRecord) -> None:
        payload = exposure_record.model_dump(mode="json")
        self.exposure_record = payload
        self.fits_header_summary = (
            exposure_record.fits_header.model_dump(mode="json")
            if exposure_record.fits_header is not None
            else None
        )
        self.data_products = []
        if exposure_record.primary_data_product is not None:
            self.data_products.append(
                exposure_record.primary_data_product.model_dump(mode="json")
            )
        self.quicklooks = []
        if exposure_record.quicklook is not None:
            self.quicklooks.append(exposure_record.quicklook.model_dump(mode="json"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "obs_id": self.obs_id,
            "exp_id": self.exp_id,
            "frame_type": self.frame_type,
            "exp_time_s": self.exp_time_s,
            "state": self.state,
            "created_at_utc": self.created_at_utc,
            "started_at_utc": self.started_at_utc,
            "finished_at_utc": self.finished_at_utc,
            "operator_note": self.operator_note,
            "instrument_snapshot": self.instrument_snapshot,
            "calibration_snapshot": self.calibration_snapshot,
            "detector_config": self.detector_config,
            "preset_apply": self.preset_apply,
            "setup_context": self.setup_context,
            "data_preview": self.data_preview,
            "frame_results": self.frame_results,
            "data_products": self.data_products,
            "quicklooks": self.quicklooks,
            "fits_header_summary": self.fits_header_summary,
            "exposure_record": self.exposure_record,
        }


class ObservationFrameType(str, Enum):
    SCIENCE = "science"
    FLAT = "flat"
    ARC = "arc"
    TEST = "test"


class ExposureSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frame_type: ObservationFrameType = ObservationFrameType.SCIENCE
    exp_time_s: float = Field(..., gt=0)
    label: str | None = None


class ValidationSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: ValidationSeverity
    message: str
    field: str | None = None


class ReadinessState(str, Enum):
    READY = "ready"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"


class ReadinessItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: ReadinessState = ReadinessState.UNKNOWN
    message: str | None = None
    updated_at_utc: str | None = None

    def is_blocking(self) -> bool:
        return self.state == ReadinessState.BLOCKED


class ReadinessSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detector: ReadinessItem = Field(default_factory=ReadinessItem)
    calibration: ReadinessItem = Field(default_factory=ReadinessItem)
    slit: ReadinessItem = Field(default_factory=ReadinessItem)
    tcs: ReadinessItem = Field(
        default_factory=lambda: ReadinessItem(
            state=ReadinessState.UNAVAILABLE,
            message="TCS readiness is not implemented yet.",
        )
    )

    def blocked_components(self) -> list[str]:
        blocked: list[str] = []
        for name in ("detector", "calibration", "slit", "tcs"):
            item = getattr(self, name)
            if item.is_blocking():
                blocked.append(name)
        return blocked

    def is_blocked(self) -> bool:
        return bool(self.blocked_components())


class ObservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str | None = None
    target_name: str | None = None
    exposures: list[ExposureSpec] = Field(..., min_length=1)
    operator_note: str | None = None
    setup_context: dict[str, Any] | None = None

    def single_exposure_spec(self) -> ExposureSpec | None:
        if len(self.exposures) != 1:
            return None
        return self.exposures[0]

    def compatibility_issues(self) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []

        if len(self.exposures) != 1:
            issues.append(
                ValidationIssue(
                    code="multiple_exposures_not_supported",
                    severity=ValidationSeverity.ERROR,
                    field="exposures",
                    message=(
                        "Initial observation preview compatibility requires "
                        "exactly one ExposureSpec. Multiple exposures are only "
                        "a contract shape reservation at this phase."
                    ),
                )
            )

        return issues


class ObservationPreviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: ObservationRequest
    readiness: ReadinessSnapshot
    validation_issues: list[ValidationIssue]
    side_effect_free: bool
    single_exposure_compatible: bool
    blocked: bool

    @classmethod
    def from_request(
        cls,
        request: ObservationRequest,
        *,
        readiness: ReadinessSnapshot | None = None,
        validation_issues: list[ValidationIssue] | None = None,
    ) -> "ObservationPreviewResult":
        readiness = readiness or ReadinessSnapshot()
        issues = list(request.compatibility_issues())

        if validation_issues:
            issues.extend(validation_issues)

        has_error = any(issue.severity == ValidationSeverity.ERROR for issue in issues)
        blocked = has_error or readiness.is_blocked()

        return cls(
            request=request,
            readiness=readiness,
            validation_issues=issues,
            side_effect_free=True,
            single_exposure_compatible=(
                request.single_exposure_spec() is not None and not blocked
            ),
            blocked=blocked,
        )


class ObservationCommandName(str, Enum):
    STATUS = "status"
    PREVIEW = "preview"
    ARM = "arm"
    START = "start"
    FINISH = "finish"
    STOP_READOUT = "stop_readout"
    ABORT_DISCARD = "abort_discard"


class ObservationCommandStatus(str, Enum):
    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    FAILED = "failed"


class ObservationCommandBlockedReason(str, Enum):
    READINESS_GATE = "readiness_gate"
    INTERLOCK = "interlock"
    VALIDATION = "validation"
    API_ERROR = "api_error"
    UNKNOWN = "unknown"


class ObservationCommandError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: dict[str, Any] | None = None


class ObservationCommandFeedback(BaseModel):
    """Normalized feedback for an observation command.

    Preview remains an advisory/readiness command. Arm remains an explicit command
    and must run its own backend readiness gate at execution time. A blocked arm
    may include the backend gate's preview snapshot, but that snapshot is not a
    prerequisite produced by the UI Preview action.
    """

    model_config = ConfigDict(extra="forbid")

    command: ObservationCommandName
    ok: bool
    status: ObservationCommandStatus
    message: str | None = None
    request_id: str | None = None
    observation_state: str | None = None
    latest_job: dict[str, Any] | None = None
    error: ObservationCommandError | None = None
    blocked: bool = False
    blocked_reason: ObservationCommandBlockedReason | None = None
    blocked_components: list[str] = Field(default_factory=list)
    preview: ObservationPreviewResult | None = None
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def succeeded(
        cls,
        command: ObservationCommandName | str,
        *,
        message: str | None = None,
        request_id: str | None = None,
        observation_state: str | None = None,
        latest_job: dict[str, Any] | None = None,
        preview: ObservationPreviewResult | None = None,
        details: dict[str, Any] | None = None,
    ) -> "ObservationCommandFeedback":
        return cls(
            command=ObservationCommandName(command),
            ok=True,
            status=ObservationCommandStatus.SUCCEEDED,
            message=message,
            request_id=request_id,
            observation_state=observation_state,
            latest_job=latest_job,
            blocked=False,
            preview=preview,
            validation_issues=list(preview.validation_issues) if preview else [],
            details=details or {},
        )

    @classmethod
    def blocked_by_readiness_gate(
        cls,
        command: ObservationCommandName | str,
        *,
        message: str | None = None,
        request_id: str | None = None,
        preview: ObservationPreviewResult | None = None,
        blocked_components: list[str] | None = None,
        error: ObservationCommandError | None = None,
        details: dict[str, Any] | None = None,
    ) -> "ObservationCommandFeedback":
        if preview is not None:
            components = blocked_components or preview.readiness.blocked_components()
            issues = list(preview.validation_issues)
        else:
            components = blocked_components or []
            issues = []

        return cls(
            command=ObservationCommandName(command),
            ok=False,
            status=ObservationCommandStatus.BLOCKED,
            message=message or "Observation command blocked by readiness gate.",
            request_id=request_id,
            error=error,
            blocked=True,
            blocked_reason=ObservationCommandBlockedReason.READINESS_GATE,
            blocked_components=components,
            preview=preview,
            validation_issues=issues,
            details=details or {},
        )

    @classmethod
    def failed(
        cls,
        command: ObservationCommandName | str,
        *,
        message: str | None = None,
        request_id: str | None = None,
        error: ObservationCommandError | None = None,
        details: dict[str, Any] | None = None,
    ) -> "ObservationCommandFeedback":
        return cls(
            command=ObservationCommandName(command),
            ok=False,
            status=ObservationCommandStatus.FAILED,
            message=message,
            request_id=request_id,
            error=error,
            blocked=False,
            details=details or {},
        )
