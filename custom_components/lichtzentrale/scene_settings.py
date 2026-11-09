# Geändert für Lichtzentrale
"""Per-scene lamp settings; capabilities and grants stay runtime-owned."""

from copy import deepcopy

from homeassistant.exceptions import ServiceValidationError

from .rooms import validate_control_options

MODES = {"cycle", "fixed", "moon", "off"}
MOON_DEFAULTS = {"new_brightness": 26, "full_brightness": 204, "new_xy": [0.25, 0.27],
                 "full_xy": [0.3127, 0.329], "breath": False}


def validate_lamp_settings(hass, value, targets, palette=None, *, capabilities=True):
    if not isinstance(value, dict) or len(value) > 500:
        raise ServiceValidationError("Ungültige Einstellungen pro Lampe.")
    if set(value) - set(targets):
        raise ServiceValidationError("Lampenwerte dürfen die Ziele der Szene nicht erweitern.")
    result = {}
    for entity_id, raw in value.items():
        if not isinstance(raw, dict) or set(raw) - {"mode", "brightness", "xy", "color_temp_kelvin", "palette_index", "moon"}:
            raise ServiceValidationError("Ungültige Einstellung einer Lampe.")
        mode = raw.get("mode", "cycle")
        if not isinstance(mode, str) or mode not in MODES:
            raise ServiceValidationError("Unbekanntes Lampenverhalten.")
        item = {"mode": mode, "brightness": raw.get("brightness")}
        validate_control_options(brightness=item["brightness"], xy=raw.get("xy"), color_temp_kelvin=raw.get("color_temp_kelvin"))
        if "xy" in raw and raw["xy"] is None:
            raise ServiceValidationError("Bitte eine gültige feste Farbe auswählen.")
        if "color_temp_kelvin" in raw and (type(raw["color_temp_kelvin"]) is not int or not 1000 <= raw["color_temp_kelvin"] <= 40000):
            raise ServiceValidationError("Der Weißton muss zwischen 1000 und 40000 Kelvin liegen.")
        index = raw.get("palette_index")
        if index is not None and (type(index) is not int or palette is None or not 0 <= index < len(palette["colors"])):
            raise ServiceValidationError("Die feste Palettenfarbe wurde nicht gefunden.")
        if index is not None and any(raw.get(k) is not None for k in ("xy", "color_temp_kelvin")):
            raise ServiceValidationError("Bitte genau eine feste Farbe auswählen.")
        state = hass.states.get(entity_id)
        modes = set(state.attributes.get("supported_color_modes") or []) if state else set()
        onoff = entity_id.startswith("switch.") or not (modes - {"onoff", "unknown"})
        if capabilities and onoff and (item["brightness"] is not None or mode == "moon" or any(k in raw for k in ("xy", "color_temp_kelvin", "palette_index"))):
            raise ServiceValidationError("Diese Lampe unterstützt ausschließlich An / Aus.")
        if mode != "fixed" and any(k in raw for k in ("xy", "color_temp_kelvin", "palette_index")):
            raise ServiceValidationError("Eine feste Farbe benötigt das Verhalten „feste Farbe“.")
        if mode == "fixed" and not onoff and not any(raw.get(k) is not None for k in ("xy", "color_temp_kelvin", "palette_index")):
            raise ServiceValidationError("Bitte eine feste Farbe oder einen Weißton auswählen.")
        if mode != "moon" and "moon" in raw:
            raise ServiceValidationError("Mondwerte benötigen das Verhalten „Mondlicht“.")
        for key in ("xy", "color_temp_kelvin", "palette_index"):
            if key in raw:
                item[key] = deepcopy(raw[key])
        if mode == "moon":
            moon = raw.get("moon", {})
            if not isinstance(moon, dict) or set(moon) - set(MOON_DEFAULTS):
                raise ServiceValidationError("Ungültige Mondlicht-Einstellungen.")
            moon = {**deepcopy(MOON_DEFAULTS), **deepcopy(moon)}
            for prefix in ("new", "full"):
                validate_control_options(brightness=moon[prefix + "_brightness"], xy=moon[prefix + "_xy"])
                if moon[prefix + "_brightness"] is None or moon[prefix + "_xy"] is None:
                    raise ServiceValidationError("Mondlicht benötigt beide Endwerte.")
            if type(moon["breath"]) is not bool:
                raise ServiceValidationError("Atmen muss ein Wahrheitswert sein.")
            item["moon"] = moon
        result[entity_id] = item
    return result


def validate_wave_order(value, targets):
    if (not isinstance(value, list) or len(value) > 500 or any(not isinstance(v, str) for v in value)
            or len(set(value)) != len(value) or set(value) - set(targets)):
        raise ServiceValidationError("Die Wellenreihenfolge darf jede Ziellampe höchstens einmal enthalten.")
    return list(value)


def snapshot_values(scene, entity_id):
    """Resolve overrides without mutating the saved snapshot or expanding its targets."""
    value = deepcopy(scene["lights"][entity_id])
    setting = scene.get("lamp_settings", {}).get(entity_id, {})
    mode = setting.get("mode", "cycle")
    if mode == "off":
        return {"on": False}
    if mode == "moon":
        from .moon import light_values

        value = {"on": True, **light_values(setting.get("moon"))}
        if setting.get("brightness") is not None:
            value["brightness"] = setting["brightness"]
        return value
    if mode == "fixed":
        value = {"on": True, **({"brightness": value["brightness"]} if "brightness" in value else {}),
                 **{k: deepcopy(setting[k]) for k in ("xy", "color_temp_kelvin") if k in setting}}
    if value.get("on"):
        bri = setting.get("brightness")
        if bri is None:
            bri = scene.get("brightness")
        if bri is not None and not entity_id.startswith("switch."):
            value["brightness"] = bri
    return value
