from __future__ import annotations

from justls.ics.adapters.detector.adapter import SimDetectorAdapter
from justls.ics.adapters.lamps.adapter import SimCalibrationAdapter
from justls.ics.adapters.slit.adapter import SimSlitAdapter
from justls.ics.drivers.sim.detector_driver import SimDetectorDriver
from justls.ics.drivers.sim.lamp_driver import (
    CalibrationLampType,
    CalibrationMode,
    SimCalibrationDriver,
)
from justls.ics.drivers.sim.slit_driver import SimSlitDriver

from .detector_contract import (
    assert_detector_abort_contract,
    assert_detector_exposure_contract,
)


def test_sim_detector_adapter_exposure_contract() -> None:
    adapter = SimDetectorAdapter(SimDetectorDriver())
    assert_detector_exposure_contract(adapter)


def test_sim_detector_adapter_abort_contract() -> None:
    adapter = SimDetectorAdapter(SimDetectorDriver())
    assert_detector_abort_contract(adapter)


def test_sim_slit_adapter_position_contract() -> None:
    adapter = SimSlitAdapter(SimSlitDriver())

    adapter.set_width_um(180.0)
    adapter.set_angle_deg(7.5)

    assert adapter.get_width_um() == 180.0
    assert adapter.get_angle_deg() == 7.5


def test_sim_calibration_adapter_state_contract() -> None:
    adapter = SimCalibrationAdapter(SimCalibrationDriver())

    adapter.set_mode(CalibrationMode.CALIBRATION)
    adapter.set_active_lamp(CalibrationLampType.ARC_NE)
    adapter.set_lamp_enabled(True)

    assert adapter.get_mode() == CalibrationMode.CALIBRATION
    assert adapter.get_active_lamp() == CalibrationLampType.ARC_NE
    assert adapter.is_lamp_enabled() is True
    assert adapter.is_mirror_inserted() is True

    adapter.set_lamp_enabled(False)

    assert adapter.get_mode() == CalibrationMode.SCIENCE
    assert adapter.get_active_lamp() is None
    assert adapter.is_lamp_enabled() is False
    assert adapter.is_mirror_inserted() is False
