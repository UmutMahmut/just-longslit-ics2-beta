from justls.ics.infra.acquisition_settings import describe, validated_settings
from justls.ics.drivers.zwo.sdk import ASI_GAIN, ASI_OFFSET, ASI_IMG_RAW16


def configure(driver, updates):
    # Caller owns the driver's lock and Runtime acquisition ownership guard.
    values = validated_settings(driver, updates)
    if getattr(driver, '_active', None) is not None:
        from justls.ics.kernel.errors import InvalidStateError
        raise InvalidStateError('Camera has an active exposure')
    session = driver._require_session()
    session.set_roi_format(width=values['width'], height=values['height'],
                           binning=values['binning'], image_type=ASI_IMG_RAW16)
    gain, _ = session.set_control_value(ASI_GAIN, values['gain'])
    offset, _ = session.set_control_value(ASI_OFFSET, values['offset'])
    if 'cooler_enabled' in updates or 'cooler_target_c' in updates:
        driver.set_cooling(enabled=values['cooler_enabled'], target_temperature_c=values['cooler_target_c'])
    driver.width, driver.height, driver.binning = values['width'], values['height'], values['binning']
    driver.gain, driver.offset = gain, offset
    driver.config = driver.config.model_copy(update={'preview_exposure_ms': values['preview_exposure_ms']})
    return describe(driver)
