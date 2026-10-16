from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from justls.ics.adapters.detector.adapter import BaseDetectorAdapter
from justls.ics.domain.observation.models import (
    ExposureRecord,
    FrameResult,
    ObservationMeta,
    utc_now_iso,
    validate_exposure_time,
)
from justls.ics.kernel.errors import InvalidParamError, InvalidStateError
from justls.ics.kernel.states import ExposureState


@dataclass(slots=True)
class ArmedExposure:
    obs_id: str
    exp_id: str
    exp_time_s: float
    frame_type: str
    save_requested: bool
    operator_note: str | None = None

    def to_dict(self) -> dict:
        return {
            "obs_id": self.obs_id,
            "exp_id": self.exp_id,
            "exp_time_s": self.exp_time_s,
            "frame_type": self.frame_type,
            "save_requested": self.save_requested,
            "operator_note": self.operator_note,
        }


@dataclass(slots=True)
class ExposureSnapshot:
    state: ExposureState
    armed_exposure: dict | None
    last_exposure: dict | None
    observation_meta: dict | None
    latest_exposure_record: dict | None
    camera_status: dict | None

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "armed_exposure": self.armed_exposure,
            "last_exposure": self.last_exposure,
            "observation_meta": self.observation_meta,
            "latest_exposure_record": self.latest_exposure_record,
            "camera_status": self.camera_status,
        }


class DetectorSubsystem:
    def __init__(self, adapter: BaseDetectorAdapter) -> None:
        self.adapter = adapter
        self._state = ExposureState.READY_TO_ARM
        self._armed: ArmedExposure | None = None
        self._last_exposure: dict | None = None
        self._observation_meta: ObservationMeta | None = None
        self._latest_exposure_record: dict | None = None

    @property
    def state(self) -> ExposureState:
        return self._state

    def get_snapshot(self) -> ExposureSnapshot:
        return ExposureSnapshot(
            state=self._state,
            armed_exposure=self._armed.to_dict() if self._armed is not None else None,
            last_exposure=self._last_exposure,
            observation_meta=self._observation_meta.to_dict() if self._observation_meta is not None else None,
            latest_exposure_record=self._latest_exposure_record,
            camera_status=self.adapter.get_status(),
        )

    def mark_failed(self) -> None:
        self._state = ExposureState.FAILED

    def arm(
        self,
        *,
        exp_time_s: float,
        frame_type: str = "science",
        save_requested: bool = False,
        operator_note: str | None = None,
        instrument_snapshot: dict | None = None,
        calibration_snapshot: dict | None = None,
        detector_config: dict | None = None,
        preset_apply: dict | None = None,
        setup_context: dict | None = None,
        data_preview: dict | None = None,
    ) -> ExposureSnapshot:
        exp_time_s = float(exp_time_s)

        try:
            validate_exposure_time(exp_time_s, frame_type)
        except ValueError as exc:
            raise InvalidParamError(
                str(exc),
                subsystem="detector",
                details={"exp_time_s": exp_time_s},
            ) from exc

        if self._state not in {
            ExposureState.READY_TO_ARM,
            ExposureState.COMPLETED,
            ExposureState.ABORTED,
            ExposureState.DISCARDED,
            ExposureState.FAILED,
        }:
            raise InvalidStateError(
                "detector is not ready to arm a new exposure",
                subsystem="detector",
                details={"state": self._state.value},
            )

        meta = ObservationMeta.create(
            frame_type=frame_type,
            exp_time_s=exp_time_s,
            save_requested=save_requested,
            operator_note=operator_note,
            instrument_snapshot=instrument_snapshot,
            calibration_snapshot=calibration_snapshot,
            detector_config=detector_config,
            preset_apply=preset_apply,
            setup_context=setup_context,
            data_preview=data_preview,
        )

        self._observation_meta = meta
        self._armed = ArmedExposure(
            obs_id=meta.obs_id,
            exp_id=meta.exp_id,
            exp_time_s=exp_time_s,
            frame_type=frame_type,
            save_requested=save_requested,
            operator_note=operator_note,
        )
        self._state = ExposureState.ARMED
        return self.get_snapshot()

    def start(self) -> ExposureSnapshot:
        if self._state != ExposureState.ARMED or self._armed is None or self._observation_meta is None:
            raise InvalidStateError(
                "exposure must be armed before start",
                subsystem="detector",
                details={"state": self._state.value},
            )

        self.adapter.start_exposure(
            obs_id=self._armed.obs_id,
            exp_id=self._armed.exp_id,
            exp_time_s=self._armed.exp_time_s,
            frame_type=self._armed.frame_type,
            save_requested=self._armed.save_requested,
        )
        self._state = ExposureState.EXPOSING
        self._observation_meta.mark_exposing()
        return self.get_snapshot()

    def stop_and_readout(self) -> ExposureSnapshot:
        if self._state != ExposureState.EXPOSING or self._armed is None or self._observation_meta is None:
            raise InvalidStateError(
                "stop_readout is only valid while exposing",
                subsystem="detector",
                details={"state": self._state.value},
            )

        preflight = getattr(getattr(self.adapter, "driver", None), "ensure_early_readout_supported", None)
        if callable(preflight):
            preflight()
        return self._complete_exposure(early_stop=True)

    def finish_normal(self) -> ExposureSnapshot:
        if self._state != ExposureState.EXPOSING or self._armed is None or self._observation_meta is None:
            raise InvalidStateError(
                "normal readout is only valid while exposing",
                subsystem="detector",
                details={"state": self._state.value},
            )

        preflight = getattr(getattr(self.adapter, "driver", None), "ensure_readout_ready", None)
        if callable(preflight):
            preflight()
        return self._complete_exposure(early_stop=False)

    def _complete_exposure(self, *, early_stop: bool) -> ExposureSnapshot:
        if self._armed is None or self._observation_meta is None:
            raise InvalidStateError(
                "no active exposure is available for readout",
                subsystem="detector",
                details={"state": self._state.value},
            )
        self._state = ExposureState.READING_OUT
        result = (
            self.adapter.stop_exposure_and_readout()
            if early_stop
            else self.adapter.finish_exposure()
        )
        frame_result = FrameResult(
            frame_token=result.get("frame_token"),
            file_uri=result.get("file_uri"),
            kept=True,
            early_stop=early_stop,
            discarded=False,
            checksum=result.get("checksum"),
            started_at_utc=result.get("started_at"),
            finished_at_utc=result.get("finished_at"),
            result="completed",
            save_requested=self._armed.save_requested,
            quicklook_uri=result.get("quicklook_uri"),
            exists=bool(result.get("exists")),
            simulated=bool(result.get("simulated", False)),
            physical_camera_id=result.get("physical_camera_id"),
            logical_channels=tuple(result.get("logical_channels") or ()),
            shared_capture_id=result.get("shared_capture_id"),
            requested_exp_time_s=result.get(
                "requested_exp_time_s",
                self._armed.exp_time_s,
            ),
            actual_exp_time_s=result.get("actual_exp_time_s"),
            detector_metadata=result.get("detector_metadata"),
            quicklook_checksum=result.get("quicklook_checksum"),
            file_size_bytes=result.get("file_size_bytes"),
            quicklook_size_bytes=result.get("quicklook_size_bytes"),
            fits_header_cards=result.get("fits_header_cards"),
        )
        result.update(
            {
                "kept": True,
                "early_stop": early_stop,
                "discarded": False,
                "exp_id": self._armed.exp_id,
                "operator_note": self._armed.operator_note,
            }
        )
        self._last_exposure = result
        self._observation_meta.add_frame_result(frame_result)
        self._observation_meta.mark_completed(
            finished_at_utc=result.get("finished_at")
        )
        self._attach_latest_exposure_record(frame_result)
        self._armed = None
        self._state = ExposureState.COMPLETED
        return self.get_snapshot()

    def save_last_frame(self) -> dict[str, Any]:
        """Persist the last completed frame (e.g. when saving was not armed)."""
        save = getattr(self.adapter, "save_last_frame", None)
        if not callable(save):
            raise InvalidStateError(
                "the active detector cannot save a frame after readout",
                subsystem="detector",
                details={"state": self._state.value},
            )
        if self._last_exposure is None:
            raise InvalidStateError(
                "no completed frame is available to save",
                subsystem="detector",
                details={"state": self._state.value},
            )
        if self._last_exposure.get("result") == "discarded":
            raise InvalidStateError(
                "the last exposure was discarded and cannot be saved",
                subsystem="detector",
                details={"state": self._state.value},
            )
        try:
            products = save()
        except RuntimeError as exc:
            raise InvalidStateError(
                str(exc),
                subsystem="detector",
                details={"state": self._state.value},
            ) from exc

        self._last_exposure.update(products)
        self._last_exposure["saved"] = True
        # Data-product keys (file_uri, checksum, already_saved, ...) are
        # surfaced at the top level so callers do not have to unwrap a nested
        # payload; the full fragment stays available under "products".
        return {
            "saved": True,
            "state": self._state.value,
            "frame_token": self._last_exposure.get("frame_token"),
            "products": products,
            **products,
        }

    def abort_discard(self) -> ExposureSnapshot:
        if self._state not in {ExposureState.ARMED, ExposureState.EXPOSING} or self._armed is None or self._observation_meta is None:
            raise InvalidStateError(
                "abort_discard is only valid for armed or exposing observations",
                subsystem="detector",
                details={"state": self._state.value},
            )

        finished_at = utc_now_iso()
        if self._state == ExposureState.EXPOSING:
            self.adapter.abort_exposure()

        frame_result = FrameResult(
            frame_token=None,
            file_uri=None,
            kept=False,
            early_stop=False,
            discarded=True,
            checksum=None,
            started_at_utc=self._observation_meta.started_at_utc,
            finished_at_utc=finished_at,
            result="discarded",
            save_requested=self._armed.save_requested,
            requested_exp_time_s=self._armed.exp_time_s,
        )

        self._last_exposure = {
            "obs_id": self._armed.obs_id,
            "exp_id": self._armed.exp_id,
            "frame_type": self._armed.frame_type,
            "exp_time_s": self._armed.exp_time_s,
            "save_requested": self._armed.save_requested,
            "operator_note": self._armed.operator_note,
            "frame_token": None,
            "started_at": self._observation_meta.started_at_utc,
            "finished_at": finished_at,
            "result": "discarded",
            "kept": False,
            "early_stop": False,
            "discarded": True,
        }

        self._observation_meta.add_frame_result(frame_result)
        self._observation_meta.mark_discarded(finished_at_utc=finished_at)
        self._attach_latest_exposure_record(frame_result)
        self._armed = None
        self._state = ExposureState.DISCARDED
        return self.get_snapshot()

    def _attach_latest_exposure_record(self, frame_result: FrameResult) -> None:
        if self._observation_meta is None:
            return

        exposure_record = ExposureRecord.from_frame_result(
            observation_meta=self._observation_meta,
            frame_result=frame_result,
        )
        self._observation_meta.attach_exposure_record(exposure_record)
        self._latest_exposure_record = exposure_record.model_dump(mode="json")
