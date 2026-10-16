from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator
from justls.ics.domain.detector.frame import DetectorFrameMetadata


def validate_exposure_time(seconds: float, frame_type: str) -> None:
    if not math.isfinite(seconds) or seconds < 0 or (seconds == 0 and frame_type != "bias"):
        raise ValueError("Exposure time must be positive; only Bias may request 0 s (camera minimum).")

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
    save_requested: bool = True
    quicklook_uri: str | None = None
    exists: bool = False
    simulated: bool = True
    physical_camera_id: str | None = None
    logical_channels: tuple[str, ...] = ()
    shared_capture_id: str | None = None
    requested_exp_time_s: float | None = None
    actual_exp_time_s: float | None = None
    detector_metadata: dict[str, Any] | None = None
    quicklook_checksum: str | None = None
    file_size_bytes: int | None = None
    quicklook_size_bytes: int | None = None
    fits_header_cards: dict[str, Any] | None = None

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
            "save_requested": self.save_requested,
            "quicklook_uri": self.quicklook_uri,
            "exists": self.exists,
            "simulated": self.simulated,
            "physical_camera_id": self.physical_camera_id,
            "logical_channels": list(self.logical_channels),
            "shared_capture_id": self.shared_capture_id,
            "requested_exp_time_s": self.requested_exp_time_s,
            "actual_exp_time_s": self.actual_exp_time_s,
            "detector_metadata": self.detector_metadata,
            "quicklook_checksum": self.quicklook_checksum,
            "file_size_bytes": self.file_size_bytes,
            "quicklook_size_bytes": self.quicklook_size_bytes,
            "fits_header_cards": self.fits_header_cards,
        }


class DataProductKind(str, Enum):
    FITS = "fits"
    QUICKLOOK = "quicklook"


class DataProductState(str, Enum):
    NOT_REQUESTED = "not_requested"
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
    size_bytes: int | None = Field(default=None, ge=0)
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
        size_bytes: int | None = None,
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
            size_bytes=size_bytes,
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

    @classmethod
    def not_requested(cls, *, kind: DataProductKind) -> "DataProductRef":
        return cls(
            kind=kind,
            state=DataProductState.NOT_REQUESTED,
            exists=False,
            simulated=False,
            created_at_utc=utc_now_iso(),
            message="The operator did not request a persisted data product.",
        )


class FitsHeaderSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    obs_id: str
    exp_id: str
    frame_type: str
    exp_time_s: float
    requested_exp_time_s: float
    actual_exp_time_s: float | None = None
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
        data_preview = observation_meta.data_preview or {}
        detector_profile = (
            detector_config.get("profile_name")
            if isinstance(detector_config, dict)
            else None
        )
        setup_file_stem = None
        if isinstance(data_preview, dict):
            setup_file_stem = data_preview.get("file_stem")
        if setup_file_stem is None and isinstance(setup_context, dict):
            setup_file_stem = setup_context.get("file_stem")
        simulated = frame_result.simulated if frame_result is not None else True
        requested_exp_time_s = (
            frame_result.requested_exp_time_s
            if frame_result is not None
            and frame_result.requested_exp_time_s is not None
            else observation_meta.exp_time_s
        )
        actual_exp_time_s = (
            frame_result.actual_exp_time_s if frame_result is not None else None
        )
        cards: dict[str, Any] = (
            dict(frame_result.fits_header_cards)
            if frame_result is not None and frame_result.fits_header_cards
            else {
                "OBS_ID": observation_meta.obs_id,
                "EXP_ID": observation_meta.exp_id,
                "FRAMETYP": observation_meta.frame_type.upper(),
                "EXPREQ": requested_exp_time_s,
                "EXPTIME": (
                    actual_exp_time_s
                    if actual_exp_time_s is not None
                    else requested_exp_time_s
                ),
                "DATE-OBS": (
                    frame_result.started_at_utc if frame_result is not None else None
                ),
                "DATE-END": (
                    frame_result.finished_at_utc if frame_result is not None else None
                ),
                "SAVEREQ": observation_meta.save_requested,
                "SIMULATE": simulated,
            }
        )
        if frame_result is not None:
            cards.setdefault("CAMERA", frame_result.physical_camera_id)
            cards.setdefault("SHARED", bool(frame_result.shared_capture_id))
            cards.setdefault("CHANNELS", ",".join(frame_result.logical_channels))
            if frame_result.detector_metadata is not None:
                detector_metadata = DetectorFrameMetadata.model_validate(
                    frame_result.detector_metadata
                )
                for key, value in detector_metadata.to_fits_cards().items():
                    if value is not None:
                        cards.setdefault(key, value)
        cards = {key: value for key, value in cards.items() if value is not None}
        return cls(
            obs_id=observation_meta.obs_id,
            exp_id=observation_meta.exp_id,
            frame_type=observation_meta.frame_type,
            exp_time_s=observation_meta.exp_time_s,
            requested_exp_time_s=requested_exp_time_s,
            actual_exp_time_s=actual_exp_time_s,
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
    requested_exp_time_s: float
    actual_exp_time_s: float | None = None
    state: str
    frame_token: str | None = None
    kept: bool
    early_stop: bool
    discarded: bool
    save_requested: bool = True
    started_at_utc: str | None = None
    finished_at_utc: str | None = None
    data_product: DataProductRef
    quicklook: DataProductRef | None = None
    fits_header: FitsHeaderSummary | None = None
    quality_flags: list[QualityFlag] = Field(default_factory=list)
    physical_camera_id: str | None = None
    logical_channels: list[str] = Field(default_factory=list)
    shared_capture_id: str | None = None
    detector_metadata: dict[str, Any] | None = None


class ExposureRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str = Field(default_factory=new_record_id)
    obs_id: str
    exp_id: str
    state: str
    frame_type: str
    exp_time_s: float
    requested_exp_time_s: float
    actual_exp_time_s: float | None = None
    created_at_utc: str
    started_at_utc: str | None = None
    finished_at_utc: str | None = None
    data_product_state: DataProductState
    save_requested: bool = True
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
    detector_metadata: dict[str, Any] | None = None

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

        if discarded:
            data_product = DataProductRef.not_created(
                kind=DataProductKind.FITS,
                message="Exposure was discarded; no data product was created.",
            )
            quicklook = None
            state = "discarded"
            message = "Exposure discarded; data product intentionally absent."
        elif not frame_result.save_requested:
            data_product = DataProductRef.not_requested(kind=DataProductKind.FITS)
            quicklook = None
            state = "completed"
            message = "Exposure completed; persistence was not requested."
        elif frame_result.file_uri and frame_result.exists:
            data_product = DataProductRef.available_file(
                kind=DataProductKind.FITS,
                uri=frame_result.file_uri,
                media_type="application/fits",
                checksum=frame_result.checksum,
                size_bytes=frame_result.file_size_bytes,
                simulated=frame_result.simulated,
            )
            quicklook = (
                DataProductRef.available_file(
                    kind=DataProductKind.QUICKLOOK,
                    uri=frame_result.quicklook_uri,
                    media_type="image/png",
                    checksum=frame_result.quicklook_checksum,
                    size_bytes=frame_result.quicklook_size_bytes,
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
            requested_exp_time_s=(
                frame_result.requested_exp_time_s
                if frame_result.requested_exp_time_s is not None
                else observation_meta.exp_time_s
            ),
            actual_exp_time_s=frame_result.actual_exp_time_s,
            state=state,
            frame_token=frame_result.frame_token,
            kept=frame_result.kept,
            early_stop=frame_result.early_stop,
            discarded=frame_result.discarded,
            save_requested=frame_result.save_requested,
            started_at_utc=frame_result.started_at_utc,
            finished_at_utc=frame_result.finished_at_utc,
            data_product=data_product,
            quicklook=quicklook,
            fits_header=fits_header,
            quality_flags=flags,
            physical_camera_id=frame_result.physical_camera_id,
            logical_channels=list(frame_result.logical_channels),
            shared_capture_id=frame_result.shared_capture_id,
            detector_metadata=frame_result.detector_metadata,
        )

        return cls(
            obs_id=observation_meta.obs_id,
            exp_id=observation_meta.exp_id,
            state=state,
            frame_type=observation_meta.frame_type,
            exp_time_s=observation_meta.exp_time_s,
            requested_exp_time_s=(
                frame_result.requested_exp_time_s
                if frame_result.requested_exp_time_s is not None
                else observation_meta.exp_time_s
            ),
            actual_exp_time_s=frame_result.actual_exp_time_s,
            created_at_utc=observation_meta.created_at_utc,
            started_at_utc=observation_meta.started_at_utc,
            finished_at_utc=observation_meta.finished_at_utc,
            data_product_state=data_product.state,
            save_requested=frame_result.save_requested,
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
            detector_metadata=frame_result.detector_metadata,
        )


@dataclass(slots=True)
class ObservationMeta:
    obs_id: str
    exp_id: str
    frame_type: str
    exp_time_s: float
    save_requested: bool
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
        save_requested: bool = False,
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
            save_requested=save_requested,
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
            "save_requested": self.save_requested,
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
    BIAS = "bias"
    DARK = "dark"
    FLAT = "flat"
    ARC = "arc"
    TEST = "test"


class ExposureSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frame_type: ObservationFrameType = ObservationFrameType.SCIENCE
    exp_time_s: float = Field(..., ge=0, allow_inf_nan=False)
    label: str | None = None

    @model_validator(mode="after")
    def validate_time(self):
        validate_exposure_time(self.exp_time_s, self.frame_type.value)
        return self


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
    SAVE_LAST_FRAME = "save_last_frame"


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
