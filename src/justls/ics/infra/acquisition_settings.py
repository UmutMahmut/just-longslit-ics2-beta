"""Shared settings shape; vendor commands remain in the camera driver boundary."""
from justls.ics.kernel.errors import InvalidParamError


def describe(driver) -> dict:
    config = driver.config
    descriptor = getattr(driver, "descriptor", None)
    shape = getattr(driver, "sensor_shape", (config.width, config.height))
    width = getattr(descriptor, "max_width", shape[0])
    height = getattr(descriptor, "max_height", shape[1])
    limits = getattr(driver, "control_limits", {})

    def control(number, minimum, maximum):
        cap = limits.get(number)
        return {"min": cap.minimum if cap else minimum, "max": cap.maximum if cap else maximum}

    cooling = getattr(driver, "_last_cooling", None) or {}
    exposure = control(1, 1, 2_000_000_000)
    return {
        "device_id": config.device_id,
        "driver": config.driver,
        "gain": int(getattr(driver, "gain", config.gain)),
        "offset": int(getattr(driver, "offset", config.offset)),
        "binning": int(getattr(driver, "binning", config.binning)),
        "width": int(getattr(driver, "width", config.width)),
        "height": int(getattr(driver, "height", config.height)),
        "preview_exposure_ms": config.preview_exposure_ms,
        "cooler_enabled": cooling.get("cooler_enabled", False),
        "cooler_target_c": cooling.get("cooler_target_c"),
        "pixel_format": "RAW16" if descriptor else "MONO16",
        "limits": {
            "gain": control(0, 0, 1000), "offset": control(5, 0, 1000),
            "preview_exposure_ms": {"min": exposure["min"] / 1000, "max": min(10000, exposure["max"] / 1000)},
            "exposure_s": {"min": exposure["min"] / 1e6, "max": exposure["max"] / 1e6},
            "cooler_target_c": control(16, -40, 30),
            "binning": list(getattr(descriptor, "supported_bins", (1, 2, 3, 4))),
            "sensor_width": width, "sensor_height": height,
            "cooling": bool(getattr(descriptor, "cooler", False) and callable(getattr(driver, "set_cooling", None))),
        },
    }


def validated_settings(driver, updates) -> dict:
    current = describe(driver)
    limits = current["limits"]
    values = {**{key: value for key, value in current.items() if key != "limits"}, **updates}
    for field in ("gain", "offset", "cooler_target_c", "preview_exposure_ms"):
        if field in updates:
            bounds = limits[field]
            if not bounds["min"] <= updates[field] <= bounds["max"]:
                raise InvalidParamError(f"{field} must be in [{bounds['min']}, {bounds['max']}]")
    if values["binning"] not in limits["binning"]:
        raise InvalidParamError("Unsupported binning")
    hardware = getattr(driver, "descriptor", None) is not None
    align_x, align_y = (8, 2) if hardware else (1, 1)
    if values["binning"] != current["binning"]:
        for field, alignment in (("width", align_x), ("height", align_y)):
            if field not in updates:
                value = current[field] * current["binning"] // values["binning"]
                values[field] = value - value % alignment
    if (values["width"] > limits["sensor_width"] // values["binning"]
            or values["height"] > limits["sensor_height"] // values["binning"]
            or values["width"] % align_x or values["height"] % align_y
            or min(values["width"], values["height"]) < 16):
        raise InvalidParamError("ROI exceeds the binned sensor or alignment (ZWO: width x8, height x2)")
    if ("cooler_enabled" in updates or "cooler_target_c" in updates) and not limits["cooling"]:
        raise InvalidParamError("This camera has no supported cooler")
    return values


def configure_simulated(driver, updates):
    values = validated_settings(driver, updates)
    driver.config = driver.config.model_copy(update={
        key: values[key] for key in ("gain", "offset", "binning", "width", "height", "preview_exposure_ms")
    })
    return describe(driver)
