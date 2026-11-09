# Geändert für Lichtzentrale
"""Original local palette catalogue and closed, server-side authoring validation."""

import math
import re
from copy import deepcopy
from uuid import uuid4

from homeassistant.exceptions import ServiceValidationError
from homeassistant.util.color import color_RGB_to_xy, color_xy_to_RGB

TEMPOS = {"very_slow": (180, 60), "slow": (90, 40), "medium": (30, 15), "fast": (8, 3)}
CATEGORIES = ("Herbst", "Winter", "Weihnachten", "Frühling", "Sommer", "Party", "Entspannen", "Romantik")

_LEGACY = [
    ("kupfernest", "Kupfernest", "Gemütlich", 145, ["#FFAA68", "#F36D47", "#FFD4A1"]),
    ("zimtfunken", "Zimtfunken", "Gemütlich", 115, ["#F47D50", "#D94B43", "#F8B86B"]),
    ("samtkiesel", "Samtkiesel", "Gemütlich", 95, ["#C993CF", "#E8B3BA", "#F6CDA0"]),
    ("minzpapier", "Minzpapier", "Frisch", 210, ["#94F1CF", "#C9F1E7", "#8ED0ED"]),
    ("taulinien", "Taulinien", "Frisch", 195, ["#A1DDEB", "#C7DFFA", "#CDF0C3"]),
    ("limettenfaden", "Limettenfaden", "Frisch", 225, ["#DAEC85", "#A6E7A9", "#F1E6B3"]),
    ("konfettitakt", "Konfettitakt", "Party", 220, ["#FD5BA8", "#765EF0", "#36D9CB"]),
    ("elektrobonbon", "Elektrobonbon", "Party", 235, ["#DA46EB", "#4589F3", "#FA9D43"]),
    ("diskokomet", "Diskokomet", "Party", 200, ["#EA4F68", "#46C7DD", "#D2D553"]),
    ("knospenpost", "Knospenpost", "Jahreszeiten", 190, ["#F1A8C8", "#B5DB84", "#F3D99B"]),
    ("laubgeflecht", "Laubgeflecht", "Jahreszeiten", 155, ["#DC673B", "#E7A044", "#A5AF68"]),
    ("frostsaum", "Frostsaum", "Jahreszeiten", 175, ["#ADCDF7", "#C9BBEB", "#B5E5ED"]),
]

# Authored for this integration. Legacy swatches above intentionally stay byte-for-byte.
_CURATED = [
    ("herbstglut", "Herbstglut", "Herbst", 155, "slow", ["#FF9A2E", "#FF6A13", "#D9541E", "#FFC247", "#9E2A2B"]),
    ("eichenfeuer", "Eichenfeuer", "Herbst", 135, "very_slow", ["#FFB43B", "#F07817", "#B94214", "#DE9C31"]),
    ("erntegold", "Erntegold", "Herbst", 170, "slow", ["#F6C345", "#F58B22", "#AD511D", "#C2AA49"]),
    ("eisfenster", "Eisfenster", "Winter", 165, "very_slow", ["#A6D6FF", "#E1F3FF", "#6F9DD9", "#FFDCA8"]),
    ("schneelaterne", "Schneelaterne", "Winter", 130, "slow", ["#C5E5FF", "#F0F6EB", "#FFBE65"]),
    ("polarwind", "Polarwind", "Winter", 145, "slow", ["#81C8E8", "#B2D7FE", "#DAEFEF", "#5593CF"]),
    ("tannengold", "Tannengold", "Weihnachten", 160, "slow", ["#E43E25", "#E9AF2B", "#34874C", "#FFD991"]),
    ("kerzenreigen", "Kerzenreigen", "Weihnachten", 125, "very_slow", ["#FFB14A", "#F17C25", "#FFD69A", "#B72D25"]),
    ("sternentisch", "Sternentisch", "Weihnachten", 155, "slow", ["#FFC95C", "#F5E1A3", "#C72B31", "#438D57"]),
    ("blattmorgen", "Blattmorgen", "Frühling", 190, "slow", ["#A9D85E", "#E4EE9D", "#FFC56E", "#8ECBA7"]),
    ("bluetenlicht", "Blütenlicht", "Frühling", 180, "slow", ["#FFD17E", "#FF9C74", "#DCEB96", "#B2DBCA"]),
    ("wiesentau", "Wiesentau", "Frühling", 205, "medium", ["#9DDCAB", "#CBEA92", "#F0D56B", "#9CDCE0"]),
    ("sonnenufer", "Sonnenufer", "Sommer", 205, "slow", ["#FFCB42", "#FF8C35", "#58C9D0", "#AFE6D0"]),
    ("abendterrasse", "Abendterrasse", "Sommer", 160, "very_slow", ["#FFB53D", "#EF7527", "#DEB866", "#7FAC78"]),
    ("seeglas", "Seeglas", "Sommer", 195, "slow", ["#55CEBC", "#93E3DC", "#F2D27F", "#65AAD5"]),
    ("funkenlauf", "Funkenlauf", "Party", 220, "fast", ["#FF520F", "#F5D816", "#07BFD3", "#295CEC"]),
    ("neonfluss", "Neonfluss", "Party", 225, "fast", ["#ED29A9", "#7543F0", "#13CBD0", "#92DB22"]),
    ("farbenwirbel", "Farbenwirbel", "Party", 215, "medium", ["#F22E39", "#FFAE18", "#34D084", "#355AE8", "#BC3CE2"]),
    ("holzruhe", "Holzruhe", "Entspannen", 100, "very_slow", ["#E8A452", "#FFD29A", "#C58036"]),
    ("mooslampe", "Mooslampe", "Entspannen", 105, "very_slow", ["#ACBC6C", "#DACA83", "#ECAF59", "#7C9A62"]),
    ("leisebrise", "Leise Brise", "Entspannen", 115, "very_slow", ["#9ECFCB", "#D6E5D0", "#EED3A6"]),
    ("abendkamin", "Abendkamin", "Romantik", 95, "very_slow", ["#F58C32", "#DD5228", "#FFB85C", "#A93522"]),
    ("honigherz", "Honigherz", "Romantik", 105, "slow", ["#FFB443", "#E8752C", "#FFD294", "#BE4820"]),
    ("kupferabend", "Kupferabend", "Romantik", 85, "very_slow", ["#D96329", "#F8AA58", "#A63225", "#F2C17C"]),
    ("glutseide", "Glutseide", "Romantik", 72, "very_slow", ["#9C2533", "#D36A25", "#E8A347", "#614074"]),
]


def _colors(preview):
    return [dict(zip(("x", "y"), color_RGB_to_xy(*(int(value[i:i+2], 16) for i in (1, 3, 5))), strict=True)) for value in preview]


def builtin_palettes():
    result = []
    for identifier, name, category, bri, tempo, preview in [
        *((identifier, name, category, bri, "medium" if category == "Party" else "slow", preview)
          for identifier, name, category, bri, preview in _LEGACY), *_CURATED
    ]:
        result.append({"id": identifier, "name": name, "category": category, "bri": bri,
                       "tempo": tempo, "preview": list(preview), "colors": _colors(preview), "builtin": True})
    return result


BUILTIN_PALETTES = builtin_palettes()


def list_palettes(store=None):
    result = deepcopy(BUILTIN_PALETTES)
    for value in (store.data.get("palettes", []) if store is not None else []):
        if not isinstance(value, dict) or not isinstance(value.get("id"), str):
            continue
        palette = deepcopy(value)
        colors = []
        for color in palette.get("colors", []) or []:
            pair = [color.get("x"), color.get("y")] if isinstance(color, dict) else color
            if (isinstance(pair, (list, tuple)) and len(pair) == 2 and
                    all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in pair)):
                colors.append({"x": pair[0], "y": pair[1]})
        palette["colors"] = colors
        if not palette.get("preview"):
            palette["preview"] = ["#%02X%02X%02X" % color_xy_to_RGB(color["x"], color["y"]) for color in colors]
        palette.setdefault("name", "Eigene Palette")
        palette.setdefault("category", "Eigene")
        palette.setdefault("bri", 155)
        palette.setdefault("tempo", "slow")
        palette["builtin"] = False
        result.append(palette)
    return result


def get_palette(store, palette_id, *, allow_invalid=False):
    result = next((p for p in list_palettes(store) if p["id"] == palette_id), None)
    if result is None:
        raise ServiceValidationError("Die Farbpalette wurde nicht gefunden.")
    if not allow_invalid and not result.get("colors"):
        raise ServiceValidationError("Diese gespeicherte Palette enthält keine gültigen Farben. Bitte bearbeiten.")
    return result


def validate_palette(value, existing=None):
    if not isinstance(value, dict):
        raise ServiceValidationError("Ungültige Farbpalette.")
    name, category = value.get("name"), value.get("category", "Eigene")
    if any(not isinstance(v, str) or not v.strip() or len(v.strip()) > 100 for v in (name, category)):
        raise ServiceValidationError("Name und Kategorie benötigen 1 bis 100 Zeichen.")
    preview = value.get("preview")
    if not isinstance(preview, list) or not 2 <= len(preview) <= 6 or any(
        not isinstance(v, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", v) for v in preview
    ):
        raise ServiceValidationError("Bitte 2 bis 6 gültige Farben auswählen.")
    bri, tempo = value.get("bri", 155), value.get("tempo", "slow")
    if type(bri) is not int or not 1 <= bri <= 255 or not isinstance(tempo, str) or tempo not in TEMPOS:
        raise ServiceValidationError("Ungültige Grundhelligkeit oder Tempoauswahl.")
    return {**deepcopy(existing or {}), "id": existing["id"] if existing else str(uuid4()),
            "name": name.strip(), "category": category.strip(), "bri": bri, "tempo": tempo,
            "preview": [v.upper() for v in preview], "colors": _colors(preview), "builtin": False}
