from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from justls.ics.domain.detector.config import DetectorConfig
from justls.ics.domain.observatory.context import ObservatoryContext
from justls.ics.domain.observation.sequence import SequenceExecutionSnapshot


class PresetListItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    summary: str
    category: str
    risk_level: str
    requires_confirmation: bool


class PresetListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PresetListItemResponse]


class SetupContextResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observers: str
    project_id: str
    pi_name: str
    support_operator: str
    root_name: str
    date_prefix: str
    comment: str
    next_frame_index: int
    data_directory: str
    next_frame_token: str
    file_stem: str
    fits_filename: str


class PresetChangeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    current: Any = None
    target: Any = None


class PresetPreviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preset: str
    summary: str
    category: str
    risk_level: str
    requires_confirmation: bool
    blocked: bool
    blocked_reason: str | None = None
    detector_config_changes: list[PresetChangeResponse]
    calibration_changes: list[PresetChangeResponse]
    slit_changes: list[PresetChangeResponse]
    changes: list[PresetChangeResponse]


class CalibrationStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str
    active_lamp: str | None = None
    lamp_enabled: bool
    mirror_inserted: bool


class PresetApplyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    applied_preset: str
    summary: str
    category: str
    risk_level: str
    requires_confirmation: bool
    job_id: str | None = None
    detector_config: DetectorConfig
    calibration: CalibrationStatusResponse | None = None
    calibration_applied: bool
    slit_plan: dict[str, Any] | None = None
    slit_applied: bool
    detector_config_changes: list[PresetChangeResponse] = Field(default_factory=list)
    calibration_changes: list[PresetChangeResponse] = Field(default_factory=list)
    slit_changes: list[PresetChangeResponse] = Field(default_factory=list)
    changed_fields: list[PresetChangeResponse] = Field(default_factory=list)
    skipped_fields: list[str] = Field(default_factory=list)
    blocked_fields: list[str] = Field(default_factory=list)


class ObservationExposureResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    frame_type: str | None = None
    exp_time_s: float | None = None
    operator_note: str | None = None
    result: str | None = None
    kept: bool | None = None
    early_stop: bool | None = None
    discarded: bool | None = None


class ObservationFrameResultResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    result: str | None = None
    kept: bool | None = None
    early_stop: bool | None = None
    discarded: bool | None = None
    channel: str | None = None


class DataProductRefResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str
    kind: str
    state: str
    uri: str | None = None
    exists: bool
    simulated: bool
    media_type: str | None = None
    checksum: str | None = None
    size_bytes: int | None = None
    created_at_utc: str | None = None
    message: str | None = None


class FitsHeaderSummaryResponse(BaseModel):
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


class FrameRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frame_id: str
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
    data_product: DataProductRefResponse
    quicklook: DataProductRefResponse | None = None
    fits_header: FitsHeaderSummaryResponse | None = None
    quality_flags: list[str] = Field(default_factory=list)
    physical_camera_id: str | None = None
    logical_channels: list[str] = Field(default_factory=list)
    shared_capture_id: str | None = None
    detector_metadata: dict[str, Any] | None = None


class ExposureRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str
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
    data_product_state: str
    save_requested: bool = True
    frames: list[FrameRecordResponse] = Field(default_factory=list)
    primary_data_product: DataProductRefResponse | None = None
    quicklook: DataProductRefResponse | None = None
    fits_header: FitsHeaderSummaryResponse | None = None
    quality_flags: list[str] = Field(default_factory=list)
    simulated: bool
    message: str | None = None
    physical_camera_id: str | None = None
    logical_channels: list[str] = Field(default_factory=list)
    shared_capture_id: str | None = None
    detector_metadata: dict[str, Any] | None = None


class ObservationMetaResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    obs_id: str | None = None
    exp_id: str | None = None
    frame_type: str
    exp_time_s: float
    state: str
    created_at_utc: str | None = None
    started_at_utc: str | None = None
    finished_at_utc: str | None = None
    operator_note: str | None = None
    instrument_snapshot: dict[str, Any] | None = None
    calibration_snapshot: CalibrationStatusResponse | None = None
    detector_config: DetectorConfig | None = None
    setup_context: dict[str, Any] | None = None
    data_preview: dict[str, Any] | None = None
    frame_results: list[ObservationFrameResultResponse] = Field(default_factory=list)
    data_products: list[DataProductRefResponse] = Field(default_factory=list)
    quicklooks: list[DataProductRefResponse] = Field(default_factory=list)
    fits_header_summary: FitsHeaderSummaryResponse | None = None
    exposure_record: ExposureRecordResponse | None = None


class ObservationStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str
    armed_exposure: ObservationExposureResponse | None = None
    last_exposure: ObservationExposureResponse | None = None
    observation_meta: ObservationMetaResponse | None = None
    latest_exposure_record: ExposureRecordResponse | None = None
    camera_status: dict[str, Any] | None = None


class RuntimeSubsystemStateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    state: str
    connected: bool
    updated_at: str
    message: str


class RuntimeStateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_mode: str
    overall_state: str
    exposure_state: str
    updated_at: str
    subsystems: dict[str, RuntimeSubsystemStateResponse]


class RuntimeStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    app_name: str
    version: str
    run_mode: str
    telemetry_enabled: bool
    started_at: str
    state: RuntimeStateResponse
    latest_job: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    service: str
    runtime: RuntimeStatusResponse


class StateDtoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slit_width_um: float | None = None
    slit_angle_deg: float | None = None
    lamp_on: bool = False
    temperature_c: float | None = None


class CapabilitiesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slit: bool
    slit_angle: bool
    calib_lamps: bool
    rotator: bool
    slit_monitor_camera: bool
    guider: bool
    science_channels_bgr: bool
    fast_photometry: bool


class OperationalStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: str
    summary: str
    control_state: str
    exposure_state: str
    flags: dict[str, bool]
    busy_subsystems: list[str]
    fault_subsystems: list[str]
    disconnected_subsystems: list[str]
    latest_job: dict[str, Any] | None = None
    latest_error_code: str | None = None
    stale_threshold_s: float
    refresh_hint: str
    ui_hints: dict[str, Any]


class StatusFullResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: StateDtoResponse
    capabilities: CapabilitiesResponse
    calibration: CalibrationStatusResponse | None = None
    observation: ObservationStatusResponse | None = None
    observation_sequence: SequenceExecutionSnapshot | None = None
    observatory: ObservatoryContext
    operational_status: OperationalStatusResponse
    detector_config: DetectorConfig
    hal: str
    run_mode: str
    timestamp_utc: str


class ApiErrorDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class ApiErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detail: ApiErrorDetailResponse
