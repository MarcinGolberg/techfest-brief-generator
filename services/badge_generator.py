import colorsys
import io
import json
import math
import os
import re
import unicodedata
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from openpyxl import load_workbook

from services.ai_service import extract_structured_text, generate_image_bytes, get_embedding

BRAND_GUIDELINES = {
    "primary_color": "#4A4AFF",
    "base_colors": ["#1B1B1B", "#FFFFFF"],
    "supporting_colors": ["#707070", "#F2F2F2"],
    "typography": "Graphik-like clean sans-serif",
    "geometry": "sharp corners, 0px radius",
    "motif": ">",
    "style": "professional, minimalist, premium, corporate-tech",
    "logo_rule": "use only the official Accenture logo asset, unmodified, unrotated, full opacity",
    "logo_placement": "place the full logo in one of the layout corners, with generous clear space",
    "logo_color_rule": "do not alter the color of the logo or greater-than symbol",
    "full_color_logo_background_rule": "use the full-color logo on a white background for clarity",
    "co_branding_rule": "do not create new logos or blend marks",
    "source_document": "brand.example.json",
}

LOGO_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "images", "Accenture-logo-white.png")
LOGO_PATH_DARK = os.path.join(os.path.dirname(os.path.dirname(__file__)), "images", "Accenture-logo.png")
BADGE_SIZE = (900, 1200)
SAFE_MARGIN = 56
ROLE_STRIP_WIDTH = 42
HEADER_HEIGHT = 240

ROLE_VARIANTS = [
    {
        "id": "guest",
        "label": "Gość",
        "keywords": ["gość", "gosc", "goście", "goscie", "guest", "guests", "attendee"],
        "visual_cue": "subtelny jasnoszary pasek z cienkim fioletowym akcentem",
        "accent_color": "#224BFF",
    },
    {
        "id": "client",
        "label": "Klient",
        "keywords": ["klient", "klienci", "client", "clients"],
        "visual_cue": "szeroki czarny pasek roli i czarny pionowy akcent",
        "accent_color": "#1B1B1B",
    },
    {
        "id": "partner",
        "label": "Partner",
        "keywords": ["partner", "partnerzy", "partners"],
        "visual_cue": "szeroki jasnoszary pasek roli i delikatny pionowy akcent",
        "accent_color": "#D9D9D9",
    },
    {
        "id": "organizer",
        "label": "Organizator",
        "keywords": ["organizator", "organizatorzy", "organizer", "staff", "zespół accenture"],
        "visual_cue": "szeroki pasek w kolorze Accenture Purple i mocny pionowy akcent",
        "accent_color": "#4A4AFF",
    },
    {
        "id": "speaker",
        "label": "Speaker",
        "keywords": ["prelegent", "speaker", "speakerzy", "panelista"],
        "visual_cue": "biały pasek z fioletowym akcentem i cienką ramką",
        "accent_color": "#FFFFFF",
    },
]

SAMPLE_PARTICIPANTS = {
    "guest": {
        "first_name": "Ewa",
        "last_name": "Lis",
        "company": "FinEdge",
        "position": "Conference Guest",
    },
    "client": {
        "first_name": "Anna",
        "last_name": "Nowak",
        "company": "FinCorp",
        "position": "Director of Innovation",
    },
    "partner": {
        "first_name": "Michał",
        "last_name": "Wójcik",
        "company": "Partner Solutions",
        "position": "Managing Partner",
    },
    "organizer": {
        "first_name": "Karolina",
        "last_name": "Mazur",
        "company": "Accenture",
        "position": "Event Lead",
    },
    "speaker": {
        "first_name": "Piotr",
        "last_name": "Kamiński",
        "company": "Accenture",
        "position": "AI Strategy Lead",
    },
}

ROLE_VARIANT_BY_ID = {role["id"]: role for role in ROLE_VARIANTS}

# ── Conference theme catalogue ─────────────────────────────────────────────────
# Each theme carries a `corporate` (tone=0) and `playful` (tone=1) palette pair.
# _apply_tone_to_theme() lerps between them based on the detected tone score.
#
# Visual design intent:
#   CORPORATE → near-black / monochrome / completely static / 1 invisible blob
#   PLAYFUL   → hyper-saturated multi-colour / 5 large blobs / diagonal streaks
# The contrast must be immediately obvious to the eye.
CONFERENCE_THEMES = {
    "tech_innovative": {
        "theme_id": "tech_innovative",
        "tone_cap": 1.0,
        "keywords": [
            "tech", "technology", "ai", "artificial intelligence", "digital",
            "innovation", "startup", "software", "cloud", "data", "platform",
            "cyber", "blockchain", "machine learning", "robotics", "automation",
            "saas", "api", "deep learning", "neural",
        ],
        # Near-black with a barely-visible cold-blue tint. Completely static.
        "corporate": {
            "style": "formal",
            "dynamism": 0.05,
            "gradient_stops": [
                (0.0, ( 2,  2, 10)),
                (0.5, ( 8,  5, 28)),
                (1.0, ( 3,  2, 12)),
            ],
            "blob_colors": [(12, 8, 40)],
            "blob_configs": [(0.50, 0.45, 0.40)],
            "light_streak": False,
            "text_accent": (100, 145, 210),
            "separator_color": (70, 110, 170),
            "prompt_hint": "cold precision, structured silence, digital architecture, monochrome depth",
        },
        # Molten orange erupts into hot pink — extreme heat, maximum dynamism.
        "playful": {
            "style": "innovative",
            "dynamism": 1.00,
            "gradient_stops": [
                (0.0,  ( 12,  2,  2)),
                (0.20, (200, 60,  5)),
                (0.48, (255, 90, 25)),
                (0.72, (235, 30, 85)),
                (0.88, (160, 10, 50)),
                (1.0,  ( 28,  2,  8)),
            ],
            "blob_colors": [(255, 140, 20), (255, 50, 80), (240, 100, 10), (220, 30, 100), (255, 180, 50)],
            "blob_configs": [
                (0.85, 0.08, 0.65),
                (0.12, 0.55, 0.58),
                (0.68, 0.85, 0.48),
                (0.40, 0.22, 0.40),
                (0.55, 0.60, 0.35),
            ],
            "light_streak": True,
            "text_accent": (255, 225, 155),
            "separator_color": (255, 190, 100),
            "prompt_hint": "blazing tech fire, molten orange surge, hot pink explosion, electric heat, dynamic innovation",
        },
    },
    "finance_formal": {
        "theme_id": "finance_formal",
        "tone_cap": 0.35,   # finance is structurally serious — hard ceiling on playfulness
        "keywords": [
            "finance", "financial", "banking", "investment", "capital", "trading",
            "fund", "asset", "portfolio", "fintech", "insurance", "wealth",
            "equity", "risk", "compliance", "regulatory", "audit", "accounting",
            "treasury", "private equity", "hedge", "credit",
        ],
        # Pure midnight — almost indistinguishable from black. Single faint blob.
        "corporate": {
            "style": "formal",
            "dynamism": 0.04,
            "gradient_stops": [
                (0.0, ( 2,  1,  8)),
                (0.5, ( 9,  6, 22)),
                (1.0, ( 4,  2, 10)),
            ],
            "blob_colors": [(14, 10, 32)],
            "blob_configs": [(0.50, 0.45, 0.42)],
            "light_streak": False,
            "text_accent": (195, 172, 128),
            "separator_color": (145, 125, 88),
            "prompt_hint": "midnight austerity, absolute precision, monolithic authority, unwavering control",
        },
        # "Less formal" (cap 0.35) — cold deep navy-blue, slightly brighter. Still formal, still cold.
        "playful": {
            "style": "formal",
            "dynamism": 0.28,
            "gradient_stops": [
                (0.0, ( 4,  8, 32)),
                (0.4, (12, 28, 82)),
                (0.7, (20, 50,128)),
                (1.0, ( 6, 14, 48)),
            ],
            "blob_colors": [(18, 48, 130), (28, 65, 160)],
            "blob_configs": [(0.65, 0.25, 0.44), (0.35, 0.70, 0.36)],
            "light_streak": False,
            "text_accent": (180, 205, 245),
            "separator_color": (140, 168, 215),
            "prompt_hint": "distinguished gravity, cold institutional confidence, steel authority, refined blue power",
        },
    },
    "healthcare": {
        "theme_id": "healthcare",
        "tone_cap": 0.70,
        "keywords": [
            "health", "healthcare", "medical", "pharma", "pharmaceutical",
            "clinical", "biotech", "wellness", "hospital", "medicine", "patient",
            "therapy", "life science", "diagnostics", "genomics",
        ],
        # Almost-black with a faint teal undertone. Cold, clinical, still.
        "corporate": {
            "style": "formal",
            "dynamism": 0.06,
            "gradient_stops": [
                (0.0, ( 2,  6, 12)),
                (0.5, (10, 28, 40)),
                (1.0, ( 4, 10, 20)),
            ],
            "blob_colors": [(8, 35, 52)],
            "blob_configs": [(0.50, 0.45, 0.42)],
            "light_streak": False,
            "text_accent": (110, 210, 200),
            "separator_color": (75, 175, 165),
            "prompt_hint": "clinical stillness, sterile precision, deep teal silence, life-critical calm",
        },
        # Warm amber erupts into coral — healing warmth, vibrant but capped at 0.70.
        "playful": {
            "style": "innovative",
            "dynamism": 0.78,
            "gradient_stops": [
                (0.0,  (  8,  4,  6)),
                (0.28, (185, 75, 15)),
                (0.55, (255,135, 45)),
                (0.80, (230, 65,105)),
                (1.0,  ( 18,  5, 12)),
            ],
            "blob_colors": [(255, 158, 48), (255, 90, 118), (240, 128, 28), (225, 72, 108)],
            "blob_configs": [
                (0.80, 0.12, 0.55),
                (0.18, 0.58, 0.50),
                (0.65, 0.82, 0.42),
                (0.40, 0.35, 0.35),
            ],
            "light_streak": True,
            "text_accent": (255, 222, 158),
            "separator_color": (255, 185, 108),
            "prompt_hint": "vibrant healing warmth, amber energy, coral vitality, warm wellness glow, bright life",
        },
    },
    "marketing_creative": {
        "theme_id": "marketing_creative",
        "tone_cap": 1.0,
        "keywords": [
            "marketing", "brand", "creative", "design", "advertising", "media",
            "campaign", "content", "social", "digital marketing", "agency",
            "pr", "communication", "strategy", "storytelling",
        ],
        # Very dark aubergine. Restrained, controlled. No streak.
        "corporate": {
            "style": "formal",
            "dynamism": 0.08,
            "gradient_stops": [
                (0.0, (10,  0, 22)),
                (0.5, (38,  0, 82)),
                (1.0, (16,  0, 38)),
            ],
            "blob_colors": [(50, 0, 110)],
            "blob_configs": [(0.50, 0.42, 0.44)],
            "light_streak": False,
            "text_accent": (220, 180, 245),
            "separator_color": (180, 140, 210),
            "prompt_hint": "commanding brand silence, dark authority, strategic restraint, pure creative control",
        },
        # Fire orange explodes into hot pink — maximum creative heat, chaotic and loud.
        "playful": {
            "style": "innovative",
            "dynamism": 1.00,
            "gradient_stops": [
                (0.0,  ( 18,  2,  0)),
                (0.22, (220, 62,  0)),
                (0.50, (255,102, 20)),
                (0.75, (255, 32, 82)),
                (0.90, (185, 18, 52)),
                (1.0,  ( 42,  4,  8)),
            ],
            "blob_colors": [(255, 120, 22), (255, 42, 82), (245, 82, 12), (255, 62, 122), (225, 102, 28)],
            "blob_configs": [
                (0.82, 0.08, 0.68),
                (0.15, 0.55, 0.60),
                (0.65, 0.85, 0.45),
                (0.42, 0.26, 0.38),
                (0.58, 0.55, 0.30),
            ],
            "light_streak": True,
            "text_accent": (255, 225, 162),
            "separator_color": (255, 190, 112),
            "prompt_hint": "explosive fire campaign, blazing orange energy, hot pink impact, molten creativity, maximum heat",
        },
    },
    "general": {
        "theme_id": "general",
        "tone_cap": 1.0,
        "keywords": [],
        # Near-black with a hint of Accenture purple. Completely monochrome.
        "corporate": {
            "style": "formal",
            "dynamism": 0.06,
            "gradient_stops": [
                (0.0, ( 5,  0, 15)),
                (0.5, (20,  0, 52)),
                (1.0, ( 8,  0, 22)),
            ],
            "blob_colors": [(15, 0, 42)],
            "blob_configs": [(0.50, 0.45, 0.42)],
            "light_streak": False,
            "text_accent": (185, 155, 230),
            "separator_color": (145, 115, 195),
            "prompt_hint": "refined stillness, elegant restraint, premium monochrome depth, authoritative calm",
        },
        # Warm orange bursts into rose — general warmth, vibrant and joyful.
        "playful": {
            "style": "innovative",
            "dynamism": 1.00,
            "gradient_stops": [
                (0.0,  ( 14,  2,  2)),
                (0.25, (205, 72, 18)),
                (0.55, (255,115, 32)),
                (0.80, (238, 52,105)),
                (1.0,  ( 48,  5, 15)),
            ],
            "blob_colors": [(255, 132, 28), (255, 62, 112), (242, 102, 18), (255, 82, 142), (222, 112, 38)],
            "blob_configs": [
                (0.82, 0.10, 0.65),
                (0.15, 0.60, 0.58),
                (0.68, 0.85, 0.42),
                (0.38, 0.26, 0.38),
                (0.55, 0.52, 0.30),
            ],
            "light_streak": True,
            "text_accent": (255, 222, 162),
            "separator_color": (255, 188, 112),
            "prompt_hint": "vibrant warm explosion, orange burst, rose energy, dynamic heat, joyful vibrant impact",
        },
    },
}

PARTICIPANT_COLUMN_ALIASES = {
    "full_name": {"full name", "full_name", "imie i nazwisko", "imię i nazwisko", "uczestnik", "participant"},
    "first_name": {"first name", "first_name", "imie", "imię"},
    "last_name": {"last name", "last_name", "surname", "nazwisko"},
    "company": {"company", "firma", "organization", "organisation"},
    "position": {"position", "job title", "title", "stanowisko", "funkcja"},
    "participant_type": {
        "participant type",
        "participant_type",
        "type",
        "typ",
        "typ uczestnika",
        "rola",
        "rola na konferencji",
        "conference role",
        "conference_role",
        "category",
        "kategoria",
    },
}


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _truncate(value: str, limit: int = 140) -> str:
    text = _safe_text(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def _first_non_empty(*values: Any, fallback: str = "") -> str:
    for value in values:
        text = _safe_text(value)
        if text:
            return text
    return fallback


def _normalize_key(value: Any) -> str:
    text = _safe_text(value).lower()
    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized).strip()
    return re.sub(r"\s+", " ", normalized)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", _normalize_key(value)).strip("-")
    return slug or uuid.uuid4().hex[:8]


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    return ImageColor.getrgb(value)


def _load_font(size: int, bold: bool = False):
    fonts_dir = os.path.join(os.path.dirname(__file__), "fonts")
    font_filename = "Graphik-Bold.ttf" if bold else "Graphik-Medium.ttf"
    font_path = os.path.join(fonts_dir, font_filename)

    if not os.path.exists(font_path):
        raise RuntimeError(f"Missing font file: {font_path}")

    return ImageFont.truetype(font_path, size=size)


def _fit_logo(max_width: int, max_height: int, path: str = LOGO_PATH) -> Image.Image:
    if not os.path.exists(path):
        raise ValueError(
            f"Nie znaleziono pliku logo Accenture pod ścieżką {path}. "
            "Przywróć plik logo do katalogu team4/images."
        )
    logo = Image.open(path).convert("RGBA")
    return ImageOps.contain(logo, (max_width, max_height))


def _wrap_text(text: str, draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont, max_width: int) -> List[str]:
    words = _safe_text(text).split()
    if not words:
        return []
    lines: List[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _draw_multiline(
    draw: ImageDraw.ImageDraw,
    text: str,
    position: tuple[int, int],
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    max_width: int,
    line_spacing: int = 8,
) -> int:
    x, y = position
    lines = _wrap_text(text, draw, font, max_width)
    current_y = y
    for line in lines:
        draw.text((x, current_y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, current_y), line, font=font)
        current_y = bbox[3] + line_spacing
    return current_y


def _fit_multiline_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    *,
    max_lines: int = 3,
    max_font_size: int = 118,
    min_font_size: int = 60,
    bold: bool = True,
) -> tuple[ImageFont.ImageFont, List[str], int]:
    for font_size in range(max_font_size, min_font_size - 1, -4):
        font = _load_font(font_size, bold=bold)
        lines = _wrap_text(text, draw, font, max_width)
        if not lines or len(lines) > max_lines:
            continue
        line_heights = [draw.textbbox((0, 0), line, font=font)[3] for line in lines]
        return font, lines, max(line_heights)
    fallback_font = _load_font(min_font_size, bold=bold)
    fallback_lines = _wrap_text(text, draw, fallback_font, max_width)[:max_lines] or [_safe_text(text)]
    fallback_heights = [draw.textbbox((0, 0), line, font=fallback_font)[3] for line in fallback_lines]
    return fallback_font, fallback_lines, max(fallback_heights)


def _draw_centered_lines(
    draw: ImageDraw.ImageDraw,
    lines: List[str],
    *,
    center_x: int,
    top_y: int,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
    line_spacing: int = 10,
) -> int:
    current_y = top_y
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_width = bbox[2] - bbox[0]
        line_height = bbox[3] - bbox[1]
        draw.text((center_x - (line_width // 2), current_y), line, font=font, fill=fill)
        current_y += line_height + line_spacing
    return current_y - line_spacing


def _role_bar_style(role_id: str) -> Dict[str, str]:
    styles = {
        "organizer": {
            "bar_fill": "#4A4AFF",
            "bar_text": "#FFFFFF",
            "bar_border": "#4A4AFF",
            "bar_accent": "#4A4AFF",
            "edge": "#4A4AFF",
        },
        "client": {
            "bar_fill": "#1B1B1B",
            "bar_text": "#FFFFFF",
            "bar_border": "#1B1B1B",
            "bar_accent": "#1B1B1B",
            "edge": "#1B1B1B",
        },
        "partner": {
            "bar_fill": "#C0BCBC",
            "bar_text": "#1B1B1B",
            "bar_border": "#C0BCBC",
            "bar_accent": "#C0BCBC",
            "edge": "#C0BCBC",
        },
        "speaker": {
            "bar_fill": "#FFFFFF",
            "bar_text": "#1B1B1B",
            "bar_border": "#D9D9D9",
            "bar_accent": "#4A4AFF",
            "edge": "#4A4AFF",
        },
        "guest": {
            "bar_fill": "#224BFF",
            "bar_text": "#FFFFFF",
            "bar_border": "#224BFF",
            "bar_accent": "#224BFF",
            "edge": "#224BFF",
        },
    }
    return styles.get(role_id, styles["guest"])


# ── Gradient background helpers ───────────────────────────────────────────────

def _lerp_color(c1: tuple, c2: tuple, t: float) -> tuple:
    t = max(0.0, min(1.0, t))
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def _rgb_to_hls(rgb: tuple) -> tuple:
    r, g, b = rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0
    return colorsys.rgb_to_hls(r, g, b)


def _hls_to_rgb(h: float, l: float, s: float) -> tuple:
    r, g, b = colorsys.hls_to_rgb(h, max(0.0, min(1.0, l)), max(0.0, min(1.0, s)))
    return (int(r * 255), int(g * 255), int(b * 255))


def _apply_tone_to_color_sat_bright(rgb: tuple, tone: float) -> tuple:
    """Modulate saturation and brightness of a color based on tone [0,1].

    tone=0 (corporate) → keep as-is (dark, desaturated)
    tone=1 (playful)   → push toward vivid: target L=0.60, target S=0.90

    The HUE is never touched — the badge colour identity stays constant across
    the corporate-playful axis.  Only energy and vividness change.
    """
    tone = max(0.0, min(1.0, tone))
    h, l, s = _rgb_to_hls(rgb)
    TARGET_L = 0.60
    TARGET_S = 0.90
    l_new = l + tone * max(0.0, TARGET_L - l)
    s_new = s + tone * max(0.0, TARGET_S - s)
    return _hls_to_rgb(h, l_new, s_new)


def _apply_tone_to_gradient_stops(stops: List[tuple], tone: float) -> List[tuple]:
    """Apply tone-based saturation/brightness modulation to every gradient stop."""
    return [(pos, _apply_tone_to_color_sat_bright(color, tone)) for pos, color in stops]


def _inject_industry_hue_into_stops(stops: List[tuple], industry_rgb: tuple) -> List[tuple]:
    """Replace the hue in each gradient stop with the industry colour's hue,
    preserving each stop's original lightness and saturation structure."""
    ind_h, _, ind_s = _rgb_to_hls(industry_rgb)
    result = []
    for pos, color in stops:
        stop_hls = _rgb_to_hls(color)
        l, s = stop_hls[1], stop_hls[2]
        # If the stop is near-achromatic, borrow a fraction of the industry saturation
        effective_s = s if s > 0.05 else ind_s * 0.4
        result.append((pos, _hls_to_rgb(ind_h, l, effective_s)))
    return result


def _hex_list_to_gradient_stops(hex_rgb_list: List[tuple]) -> List[tuple]:
    """Distribute a list of (R,G,B) colors evenly as gradient stops [0.0 … 1.0]."""
    n = len(hex_rgb_list)
    if n == 1:
        return [(0.0, hex_rgb_list[0]), (1.0, hex_rgb_list[0])]
    return [(i / (n - 1), hex_rgb_list[i]) for i in range(n)]


def _sample_region_luminance(canvas: Image.Image, x1: int, y1: int, x2: int, y2: int) -> float:
    """Compute the average perceptual luminance (0–1) of a canvas region.

    Uses the sRGB relative-luminance formula: 0.2126R + 0.7152G + 0.0722B.
    Downsamples to 8×8 before averaging so the call is fast regardless of region size.
    """
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(canvas.width, x2)
    y2 = min(canvas.height, y2)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    region = canvas.crop((x1, y1, x2, y2)).convert("RGB")
    thumb = region.resize((8, 8), Image.Resampling.LANCZOS)
    pixels = list(thumb.getdata())
    if not pixels:
        return 0.0
    total = sum(
        0.2126 * (r / 255.0) + 0.7152 * (g / 255.0) + 0.0722 * (b / 255.0)
        for r, g, b in pixels
    )
    return total / len(pixels)


def _adaptive_palette(luminance: float) -> dict:
    """Return text/decoration colours that maximally contrast the given background luminance.

    luminance > 0.45 → bright background → dark text palette
    luminance ≤ 0.45 → dark  background → light text palette
    """
    if luminance > 0.45:
        return {
            "primary":   (12, 12, 22),
            "secondary": (45, 40, 65),
            "shadow":    (230, 228, 242),
            "separator": (75, 65, 105),
        }
    else:
        return {
            "primary":   (255, 255, 255),
            "secondary": (215, 205, 238),
            "shadow":    (8, 8, 18),
            "separator": (175, 155, 215),
        }


def _adapt_logo_for_background(luminance: float, max_width: int, max_height: int) -> Image.Image:
    """Load the correct Accenture logo variant based on background luminance.

    luminance > 0.45 (bright background) → Accenture-logo.png        (full-colour / dark)
    luminance ≤ 0.45 (dark  background)  → Accenture-logo-white.png  (white variant)
    """
    path = LOGO_PATH_DARK if luminance > 0.45 else LOGO_PATH
    return _fit_logo(max_width, max_height, path)


def _interpolate_gradient_stops(stops: List[tuple], t: float) -> tuple:
    t = max(0.0, min(1.0, t))
    if t <= stops[0][0]:
        return stops[0][1]
    if t >= stops[-1][0]:
        return stops[-1][1]
    for i in range(len(stops) - 1):
        p0, c0 = stops[i]
        p1, c1 = stops[i + 1]
        if p0 <= t <= p1:
            local_t = (t - p0) / (p1 - p0) if p1 > p0 else 0.0
            return _lerp_color(c0, c1, local_t)
    return stops[-1][1]


def _build_gradient_background(size: tuple, theme_info: Dict[str, Any]) -> Image.Image:
    """Build a theme- and tone-driven background.

    The visual language is deliberately extreme to make the corporate ↔ playful
    axis immediately obvious:

    CORPORATE (dynamism ≈ 0):
        Near-black base, single near-invisible blob, no streak.

    PLAYFUL (dynamism ≈ 1):
        Multi-stop saturated gradient, 5 large vivid blobs at high opacity,
        two crossing diagonal streaks.
    """
    width, height = size
    style = theme_info.get("style", "innovative")
    gradient_stops = theme_info.get("gradient_stops", [(0.0, (5, 0, 15)), (1.0, (80, 0, 190))])
    blob_colors = theme_info.get("blob_colors", [(161, 0, 255)])
    blob_configs = theme_info.get("blob_configs", [(0.75, 0.2, 0.5)])
    light_streak = theme_info.get("light_streak", False)
    dynamism = max(0.0, min(1.0, theme_info.get("dynamism", 0.5)))

    # ── Base vertical gradient ────────────────────────────────────────────────
    base = Image.new("RGB", size)
    draw = ImageDraw.Draw(base)
    for y in range(height):
        t = y / max(height - 1, 1)
        color = _interpolate_gradient_stops(gradient_stops, t)
        draw.line([(0, y), (width - 1, y)], fill=color)

    # ── Radial blobs ──────────────────────────────────────────────────────────
    # Alpha: 20 (near-invisible for corporate) → 230 (very vivid for playful).
    # Radius: scaled up by up to ×1.45 at high dynamism for bigger presence.
    blob_alpha = int(20 + dynamism * 210)
    radius_scale = 0.75 + dynamism * 0.70   # 0.75× corporate → 1.45× playful
    overlay = base.convert("RGBA")
    for i, (cx_frac, cy_frac, r_frac) in enumerate(blob_configs):
        cx = int(width * cx_frac)
        cy = int(height * cy_frac)
        radius = int(width * r_frac * radius_scale)
        color = blob_colors[i % len(blob_colors)]

        blob_layer = Image.new("RGBA", size, (0, 0, 0, 0))
        blob_draw = ImageDraw.Draw(blob_layer)
        blob_draw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius],
            fill=(*color, blob_alpha),
        )
        # Tighter blur for corporate (sharper, barely visible), softer for playful.
        blur_sigma = min(95, max(12, int(radius * (0.30 + dynamism * 0.25))))
        blob_layer = blob_layer.filter(ImageFilter.GaussianBlur(radius=blur_sigma))
        overlay = Image.alpha_composite(overlay, blob_layer)

    base = overlay.convert("RGB")

    # ── Diagonal light streaks ────────────────────────────────────────────────
    # For playful themes: two crossing bright streaks create a sense of motion.
    # Alpha rises steeply with dynamism so the streaks are invisible at tone≈0.
    if light_streak and style == "innovative":
        streak_alpha = int(dynamism * 32)   # 0 at corporate → 32 at max playful
        if streak_alpha > 0:
            streak = Image.new("RGBA", size, (0, 0, 0, 0))
            sd = ImageDraw.Draw(streak)
            # Primary diagonal slash (top-left → bottom-right direction)
            sd.polygon(
                [
                    (int(width * 0.24), 0),
                    (int(width * 0.56), 0),
                    (int(width * 0.36), height),
                    (int(width * 0.04), height),
                ],
                fill=(255, 255, 255, streak_alpha),
            )
            # Counter-diagonal slash (top-right → bottom-left) — adds chaos
            if dynamism > 0.65:
                sd.polygon(
                    [
                        (int(width * 0.55), 0),
                        (int(width * 0.80), 0),
                        (int(width * 0.62), height),
                        (int(width * 0.38), height),
                    ],
                    fill=(255, 255, 255, streak_alpha // 2),
                )
            base = Image.alpha_composite(base.convert("RGBA"), streak).convert("RGB")

    return base


def _detect_conference_theme(brief: Dict[str, Any], document_brief: Dict[str, Any]) -> Dict[str, Any]:
    """Return the best-matching CONFERENCE_THEMES entry via keyword scoring."""
    combined = " ".join([
        _safe_text(brief.get("product_or_service")),
        _safe_text(brief.get("scope_of_work")),
        _safe_text(brief.get("target_audience")),
        _safe_text(brief.get("client_expectations")),
        _safe_text(brief.get("key_messages")),
        _safe_text(document_brief.get("title")),
        _safe_text(document_brief.get("description")),
        _safe_text(document_brief.get("target_group")),
    ]).lower()

    best_id = "general"
    best_score = 0
    for theme_id, theme in CONFERENCE_THEMES.items():
        if theme_id == "general":
            continue
        score = sum(1 for kw in theme["keywords"] if kw in combined)
        if score > best_score:
            best_score = score
            best_id = theme_id

    return CONFERENCE_THEMES[best_id]


# ── Semantic tone detection ────────────────────────────────────────────────────
#
# Tone detection uses axis-projection onto the single semantic axis defined by
# the direction from the seriousness centroid to the playfulness centroid:
#
#   axis = normalize(playful_centroid - serious_centroid)
#   proj = dot(brief_vec, axis)
#   tone = (proj - proj_serious) / (proj_playful - proj_serious)   → [0, 1]
#
# This is more discriminative than comparing independent cosine similarities
# because it measures position along the specific serious↔playful axis rather
# than overall proximity to either pole in the full embedding space.
#
# Anchors: short, extreme, maximally-separated keyword phrases.  Verbose
# sentences pull the centroid toward the generic "conference/professional"
# semantic region where both poles overlap.  Tight keyword phrases stay in their
# respective extreme corners of the space.
#
# Falls back to lightweight keyword scoring if the embedding call fails.

_SERIOUSNESS_ANCHORS = [
    "audyt, compliance, regulacje, nadzor korporacyjny, zarzad, dyrektywy prawne",
    "wyniki finansowe, sprawozdawczosc, risk management, due diligence, inwestorzy",
    "instytucja finansowa, bank centralny, fundusz, nadzor regulacyjny, prawo gospodarcze",
    "formalna konferencja korporacyjna, dyrektorzy zarzadzajacy, decyzje strategiczne, rada nadzorcza",
    "procedury wewnetrzne, polityka korporacyjna, lad organizacyjny, rygorystyczne wymogi, zgodnosc",
]

_PLAYFULNESS_ANCHORS = [
    "zabawa, gry, impreza, muzyka, taniec, swietowanie, relaks, luzona atmosfera",
    "hackathon, startup, prototyp, eksperyment, kreatywnosc, spontanicznosc, energia, przygoda",
    "festiwal, spolecznosc, nieformalne spotkanie, pozytywna atmosfera, radosc, entuzjazm",
    "warsztaty tworcze, gry zespolowe, animacje, aktywnosci, interakcja, wspolna zabawa",
    "meetup, casual networking, otwarta kultura, swoboda, mloda energia, dynamizm, luz",
]

# Cached centroids and the pre-computed normalised axis vector.
# All three are computed once per process and reused across requests.
_anchor_centroids: Dict[str, Optional[List[float]]] = {
    "seriousness": None,
    "playfulness": None,
    "axis_norm": None,   # unit vector from serious → playful centroid
    "proj_serious": None,  # projection of serious centroid onto axis (calibration low bound)
    "proj_playful": None,  # projection of playful centroid onto axis (calibration high bound)
}



def _compute_centroid(phrases: List[str]) -> List[float]:
    embeddings = [get_embedding(p) for p in phrases]
    dim = len(embeddings[0])
    return [sum(emb[i] for emb in embeddings) / len(embeddings) for i in range(dim)]


def _build_tone_description(brief: Dict[str, Any], document_brief: Dict[str, Any]) -> str:
    """Build the text used for tone/sentiment detection.

    The explicit tone fields from the raw brief (tone_of_voice, client_expectations,
    target_audience) are the strongest signals and are placed first.  The LLM-enriched
    document brief fields follow for additional context.  Using the raw brief's tone
    fields is intentional here — they are direct user declarations of desired character
    (e.g. "swobodny, energiczny" vs "premium, stonowany") that the LLM enrichment step
    tends to neutralise into formal prose.
    """
    key_points_text = " ".join(_safe_list(document_brief.get("key_points")))
    return " ".join(filter(None, [
        # Explicit tone declarations from raw brief — highest signal quality
        _safe_text(brief.get("tone_of_voice")),
        _safe_text(brief.get("client_expectations")),
        _safe_text(brief.get("target_audience")),
        _safe_text(brief.get("campaign_goal")),
        # Document brief — context and industry
        _safe_text(document_brief.get("title")),
        _safe_text(document_brief.get("executive_summary")),
        _safe_text(document_brief.get("target_group")),
        _safe_text(document_brief.get("insight")),
        _safe_text(document_brief.get("creative_challenge")),
        key_points_text,
    ]))


def _detect_tone_keyword_fallback(brief: Dict[str, Any], document_brief: Dict[str, Any]) -> float:
    """Lightweight keyword-based fallback when embeddings are unavailable."""
    corporate_kw = {
        # English
        "enterprise", "executive", "board", "boardroom", "governance", "compliance",
        "regulatory", "stakeholder", "shareholder", "strategic", "formal",
        "professional", "corporate", "due diligence", "fiduciary",
        # Polish — explicit tone words from briefs
        "elegancki", "eleganckie", "stonowany", "stonowane", "premium",
        "powściągliwy", "powściągliwe", "prestiżowy", "prestiżowe",
        "ekskluzywny", "ekskluzywne", "reprezentacyjny", "bez krzykliwości",
        "wyrafinowany", "wyrafinowane", "profesjonalny", "profesjonalne",
        # Polish — corporate context
        "zarząd", "regulacje", "instytucjonalne", "korporacyjne", "finansowy",
        "inwestorzy", "compliance", "audyt",
    }
    playful_kw = {
        # English
        "startup", "hackathon", "festival", "fun", "creative", "casual",
        "workshop", "bootcamp", "celebrate", "maker", "meetup",
        # Polish — explicit tone words from briefs
        "zabawowy", "zabawowe", "energiczny", "energiczne", "progresywny",
        "progresywne", "swobodny", "swobodne", "kreatywny", "kreatywne",
        "krzykliwy", "krzykliwe", "dynamiczny", "dynamiczne", "luźny", "luźne",
        "radosny", "radosne", "festiwalowy", "festiwalowe", "nieformalne",
        # Polish — playful context
        "zabawa", "festiwal", "swietowanie", "społeczność", "warsztaty",
        "hackathon", "networking", "młodzi",
    }
    combined = _build_tone_description(brief, document_brief).lower()
    corp = sum(1 for kw in corporate_kw if kw in combined)
    play = sum(1 for kw in playful_kw if kw in combined)
    total = corp + play
    if total == 0:
        return 0.20
    return max(0.0, min(1.0, play / total))


def _detect_tone(brief: Dict[str, Any], document_brief: Dict[str, Any]) -> float:
    """Return a tone score 0.0 (very corporate/serious) -> 1.0 (very playful/free).

    Uses axis-projection onto the semantic axis from seriousness to playfulness:
      1. Compute unit vector from serious centroid to playful centroid.
      2. Project the brief embedding onto that axis.
      3. Calibrate with anchor projections; normalise to [0, 1].

    The description is built from both the raw brief's explicit tone fields
    (tone_of_voice, client_expectations) and the enriched document brief.

    Falls back to keyword scoring when the embedding service is unavailable.
    """
    description = _build_tone_description(brief, document_brief)
    if not description.strip():
        return 0.20

    try:
        global _anchor_centroids
        # Build and cache centroids + axis on first call
        if _anchor_centroids["seriousness"] is None:
            _anchor_centroids["seriousness"] = _compute_centroid(_SERIOUSNESS_ANCHORS)
        if _anchor_centroids["playfulness"] is None:
            _anchor_centroids["playfulness"] = _compute_centroid(_PLAYFULNESS_ANCHORS)

        if _anchor_centroids["axis_norm"] is None:
            serious_c = _anchor_centroids["seriousness"]
            playful_c = _anchor_centroids["playfulness"]
            # Raw axis: direction from serious pole to playful pole
            raw_axis = [p - s for p, s in zip(playful_c, serious_c)]
            mag = math.sqrt(sum(x * x for x in raw_axis))
            if math.isclose(mag, 0.0, abs_tol=1e-09):
                return _detect_tone_keyword_fallback(brief, document_brief)
            axis_norm = [x / mag for x in raw_axis]
            _anchor_centroids["axis_norm"] = axis_norm
            # Calibration: where do the anchor centroids themselves land on this axis?
            _anchor_centroids["proj_serious"] = sum(s * a for s, a in zip(serious_c, axis_norm))
            _anchor_centroids["proj_playful"] = sum(p * a for p, a in zip(playful_c, axis_norm))

        axis_norm = _anchor_centroids["axis_norm"]
        proj_serious = _anchor_centroids["proj_serious"]
        proj_playful = _anchor_centroids["proj_playful"]
        span = proj_playful - proj_serious  # always > 0 by construction

        brief_vec = get_embedding(description[:3000])
        proj_brief = sum(b * a for b, a in zip(brief_vec, axis_norm))

        # Normalise: 0.0 = at the serious anchor centroid, 1.0 = at the playful centroid.
        # Apply a soft ceiling (0.9) — real briefs rarely reach pure-festival extremity.
        raw = (proj_brief - proj_serious) / span
        tone = max(0.0, min(1.0, raw * 0.9))
        return tone

    except Exception:
        return _detect_tone_keyword_fallback(brief, document_brief)


def _apply_tone_to_theme(
    theme_info: Dict[str, Any],
    tone: float,
    industry_colors: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Resolve the corporate palette for the given tone [0, 1].

    Color identity (hue) is preserved across the full tone range.
    Only saturation and brightness are modulated:
        tone=0  → dark, desaturated  (corporate feel)
        tone=1  → vivid, bright      (playful feel)

    If industry_colors are supplied (from _extract_industry_colors), the
    primary industry hue is injected into the base gradient stops before
    the saturation/brightness modulation, so the badge reflects the
    industry's psychological color identity.

    Structural elements (dynamism, blob_configs, light_streak) still blend
    between the corporate and playful extremes as before.

    tone_cap clips the maximum playfulness for inherently formal domains.
    """
    tone = max(0.0, min(1.0, tone))
    tone = min(tone, theme_info.get("tone_cap", 1.0))

    corp = theme_info["corporate"]
    play = theme_info["playful"]

    # ── Gradient stops ────────────────────────────────────────────────────────
    # Priority:
    #   1. GPT-4o multi-color palette  → diverse, industry-specific, rich gradient
    #   2. Industry primary hue inject → single-hue variant (fallback)
    #   3. Corporate palette           → default dark theme
    # In all cases tone modulates saturation + brightness (never the hue).
    gpt_stops = (industry_colors or {}).get("gradient_stops_rgb")
    if gpt_stops:
        base_stops = _hex_list_to_gradient_stops(gpt_stops)
    elif industry_colors and industry_colors.get("primary"):
        base_stops = _inject_industry_hue_into_stops(corp["gradient_stops"], industry_colors["primary"])
    else:
        base_stops = corp["gradient_stops"]
    gradient_stops = _apply_tone_to_gradient_stops(base_stops, tone)

    # ── Blob colours: use corporate hue (or industry secondary) + tone sat/bright
    base_blob_colors = corp["blob_colors"]
    if industry_colors and industry_colors.get("secondary"):
        base_blob_colors = [industry_colors["secondary"]] * len(base_blob_colors)
    blob_colors = [_apply_tone_to_color_sat_bright(c, tone) for c in base_blob_colors]

    # ── Blob positions switch at midpoint (structural, not colour-related) ───
    blob_configs = corp["blob_configs"] if tone <= 0.50 else play["blob_configs"]

    # ── Structural elements — linear blend as before ─────────────────────────
    dynamism = corp["dynamism"] + (play["dynamism"] - corp["dynamism"]) * tone
    style = play["style"] if tone > 0.50 else corp["style"]
    light_streak = play["light_streak"] if tone > 0.60 else corp["light_streak"]

    # Text / separator accents: sat+bright modulated from corporate base
    text_accent = _apply_tone_to_color_sat_bright(corp["text_accent"], 0.4 + 0.6 * tone)
    separator_color = _apply_tone_to_color_sat_bright(corp["separator_color"], 0.4 + 0.6 * tone)

    prompt_hint = play["prompt_hint"] if tone > 0.50 else corp["prompt_hint"]

    return {
        "theme_id": theme_info["theme_id"],
        "style": style,
        "dynamism": dynamism,
        "gradient_stops": gradient_stops,
        "blob_colors": blob_colors,
        "blob_configs": blob_configs,
        "light_streak": light_streak,
        "text_accent": text_accent,
        "separator_color": separator_color,
        "prompt_hint": prompt_hint,
        "tone": tone,
        "industry_colors": industry_colors,
    }


def _open_generated_background(image_bytes: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return ImageOps.fit(image, BADGE_SIZE, method=Image.Resampling.LANCZOS)


def _compose_badge_image(badge: Dict[str, Any], image_bytes: bytes) -> bytes:
    """Compose the final badge image.

    Background: a theme-driven purple gradient (dynamic blobs for innovative
    themes, clean linear for formal themes). The AI-generated image is blended
    in at very low opacity as an organic texture layer so the keyword-enriched
    prompt still influences the final look without overwhelming the gradient.
    All foreground text is rendered in white/light-lavender tones for contrast.
    The Accenture logo sits on a white panel at the bottom (brand-compliance
    rule: full-colour logo must appear on white).
    """
    theme_info = badge.get("themeInfo") or CONFERENCE_THEMES["general"]
    style = theme_info.get("style", "innovative")

    # ── Background: gradient + subtle AI texture ──────────────────────────────
    gradient = _build_gradient_background(BADGE_SIZE, theme_info)
    ai_texture = _open_generated_background(image_bytes)
    ai_texture = ImageEnhance.Color(ai_texture).enhance(0.35)
    ai_texture = ImageEnhance.Brightness(ai_texture).enhance(0.30)
    ai_opacity = 0.12 if style == "innovative" else 0.06
    canvas_rgb = Image.blend(gradient, ai_texture, ai_opacity)

    width, height = canvas_rgb.size

    # ── Subtle polygon overlays for visual depth ──────────────────────────────
    overlay = Image.new("RGBA", BADGE_SIZE, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.polygon(
        [(0, 0), (int(width * 0.42), 0), (int(width * 0.22), height), (0, height)],
        fill=(255, 255, 255, 10),
    )
    canvas = Image.alpha_composite(canvas_rgb.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(canvas)

    # ── Adaptive colour palette based on actual background luminance ──────────
    # Sample BEFORE any text/shapes are drawn so colours reflect the real bg.
    # Two zones: content (title → separator) and logo strip (below role bar).
    _content_lum = _sample_region_luminance(canvas, 0, 0, width, int(height * 0.68))
    _logo_lum    = _sample_region_luminance(canvas, 0, int(height * 0.78), width, height)
    text_pal     = _adaptive_palette(_content_lum)
    logo         = _adapt_logo_for_background(_logo_lum, max_width=480, max_height=180)

    # ── Extract badge data ────────────────────────────────────────────────────
    layout_data = badge.get("badgeLayoutData") or {}
    participant = layout_data.get("participant") or {}
    layout = layout_data.get("layout") or {}
    attendee_name = _safe_text(participant.get("fullName")) or " ".join(
        part for part in [participant.get("firstName"), participant.get("lastName")] if _safe_text(part)
    ).strip() or "Jan Kowalski"
    conference_name = (
        _safe_text(layout_data.get("conferenceName"))
        or _safe_text(badge.get("conference_name"))
        or _safe_text(badge.get("headline"))
    )
    role_id = _safe_text(participant.get("participantTypeId") or badge.get("role_id") or "guest")
    role_text = _safe_text(participant.get("participantType") or badge.get("participant_type")).upper()
    secondary_text = _safe_text(layout.get("secondaryText"))
    show_secondary_text = bool(layout.get("showSecondaryText")) and bool(secondary_text)
    company_text = _safe_text(participant.get("company"))
    position_text = _safe_text(participant.get("position"))
    role_style = _role_bar_style(role_id)

    card_left = 0
    card_top = 0
    card_right = width
    card_bottom = height
    edge_width = 28

    # ── Right-edge role colour strip ──────────────────────────────────────────
    edge_color = _hex_to_rgb(role_style["edge"])
    draw.rectangle(
        (card_right - edge_width, card_top, card_right, card_bottom),
        fill=edge_color,
    )

    # ── Fonts ─────────────────────────────────────────────────────────────────
    title_font = _load_font(42, bold=False)
    role_font = _load_font(48, bold=True)
    company_font = _load_font(48, bold=True)
    position_font = _load_font(42, bold=False)
    secondary_font = _load_font(30, bold=False)
    # logo is already built adaptively above (logo / logo_base)

    content_left = card_left + 72
    content_right = card_right - edge_width - 64
    content_width = content_right - content_left
    center_x = (content_left + content_right) // 2

    # ── Conference name ───────────────────────────────────────────────────────
    title_lines = _wrap_text(_truncate(conference_name, 80), draw, title_font, content_width)
    current_y = card_top + 86
    for line in title_lines[:2]:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        line_width = bbox[2] - bbox[0]
        line_height = bbox[3] - bbox[1]
        x = center_x - (line_width // 2)
        draw.text((x + 2, current_y + 2), line, font=title_font, fill=text_pal["shadow"])
        draw.text((x, current_y), line, font=title_font, fill=text_pal["primary"])
        current_y += line_height + 4

    # ── Attendee name ─────────────────────────────────────────────────────────
    name_top = card_top + 270
    name_font, name_lines, _ = _fit_multiline_text(
        draw,
        attendee_name,
        content_width,
        max_lines=3,
        max_font_size=122,
        min_font_size=72,
        bold=True,
    )
    name_bottom = _draw_centered_lines(
        draw,
        name_lines,
        center_x=center_x,
        top_y=name_top,
        font=name_font,
        fill=text_pal["primary"],
        line_spacing=10,
    )

    # ── Separator line ────────────────────────────────────────────────────────
    separator_y = name_bottom + 42
    separator_half_width = min(220, content_width // 2 - 20)
    draw.line(
        (center_x - separator_half_width, separator_y, center_x + separator_half_width, separator_y),
        fill=text_pal["separator"],
        width=2,
    )

    # ── Company / position / secondary text ──────────────────────────────────
    info_y = separator_y + 30
    if company_text:
        company_bbox = draw.textbbox((0, 0), company_text, font=company_font)
        company_width = company_bbox[2] - company_bbox[0]
        draw.text(
            (center_x - (company_width // 2), info_y),
            company_text,
            font=company_font,
            fill=text_pal["primary"],
        )
        info_y += (company_bbox[3] - company_bbox[1]) + 10

    if position_text:
        position_bbox = draw.textbbox((0, 0), position_text, font=position_font)
        position_width = position_bbox[2] - position_bbox[0]
        draw.text(
            (center_x - (position_width // 2), info_y),
            position_text,
            font=position_font,
            fill=text_pal["secondary"],
        )
        info_y += (position_bbox[3] - position_bbox[1]) + 8

    if show_secondary_text:
        secondary_bbox = draw.textbbox((0, 0), secondary_text, font=secondary_font)
        secondary_width = secondary_bbox[2] - secondary_bbox[0]
        draw.text(
            (center_x - (secondary_width // 2), info_y + 4),
            secondary_text,
            font=secondary_font,
            fill=text_pal["secondary"],
        )

    # ── Role bar ──────────────────────────────────────────────────────────────
    role_bar_height = 112
    role_bar_left = card_left
    role_bar_right = card_right - edge_width
    role_bar_top = card_bottom - 380
    role_bar_bottom = role_bar_top + role_bar_height
    draw.rectangle(
        (role_bar_left, role_bar_top, role_bar_right, role_bar_bottom),
        fill=_hex_to_rgb(role_style["bar_fill"]),
    )
    if role_id == "speaker":
        draw.rectangle(
            (role_bar_left, role_bar_top, role_bar_right, role_bar_top + 10),
            fill=_hex_to_rgb(role_style["bar_accent"]),
        )

    role_bbox = draw.textbbox((0, 0), role_text, font=role_font)
    role_text_width = role_bbox[2] - role_bbox[0]
    role_text_height = role_bbox[3] - role_bbox[1]
    draw.text(
        (
            center_x - (role_text_width // 2),
            role_bar_top + ((role_bar_height - role_text_height) // 2) - 4,
        ),
        role_text,
        font=role_font,
        fill=_hex_to_rgb(role_style["bar_text"]),
    )

    # ── Logo on white panel (brand-compliance: full-colour logo on white) ─────
    logo_area_top = role_bar_bottom
    logo_area_bottom = card_bottom
    logo_panel_padding_h = 36
    logo_panel_padding_v = 20
    logo_x = center_x - (logo.width // 2)
    logo_y = logo_area_top + (logo_area_bottom - logo_area_top - logo.height) // 2
    # draw.rectangle(
    #     (
    #         logo_x - logo_panel_padding_h,
    #         logo_y - logo_panel_padding_v,
    #         logo_x + logo.width + logo_panel_padding_h,
    #         logo_y + logo.height + logo_panel_padding_v,
    #     ),
    #     fill=(255, 255, 255),
    # )
    canvas.paste(logo, (logo_x, logo_y), logo)

    output = io.BytesIO()
    canvas.save(output, format="PNG")
    return output.getvalue()


def _detect_image_extension(image_bytes: bytes, fallback: str = "png") -> str:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "jpg"
    return fallback


def _extract_role_variants(*texts: str) -> List[Dict[str, str]]:
    combined = " ".join(_safe_text(text).lower() for text in texts if _safe_text(text))
    variants = []
    for role in ROLE_VARIANTS:
        if any(keyword in combined for keyword in role["keywords"]):
            variants.append(role)
    return variants or ROLE_VARIANTS[:3]


def _resolve_role_variant(*texts: str, fallback_id: str = "guest") -> Dict[str, str]:
    combined = " ".join(_safe_text(text).lower() for text in texts if _safe_text(text))
    for role in ROLE_VARIANTS:
        if any(keyword in combined for keyword in role["keywords"]):
            return role
    if "accenture" in combined:
        return ROLE_VARIANT_BY_ID["organizer"]
    return ROLE_VARIANT_BY_ID[fallback_id]


def _extract_role_variants_from_sources(sources: Optional[List[Dict[str, Any]]]) -> List[Dict[str, str]]:
    collected_texts: List[str] = []
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        collected_texts.append(_safe_text(source.get("filename")))
        collected_texts.append(_safe_text(source.get("content")))
    return _extract_role_variants(*collected_texts)


def _split_full_name(value: str) -> Dict[str, str]:
    parts = [part for part in _safe_text(value).split() if part]
    if not parts:
        return {"first_name": "", "last_name": ""}
    if len(parts) == 1:
        return {"first_name": parts[0], "last_name": ""}
    return {"first_name": parts[0], "last_name": " ".join(parts[1:])}


def _match_participant_columns(header_row: List[Any]) -> Dict[str, int]:
    matched: Dict[str, int] = {}
    for index, header in enumerate(header_row):
        normalized_header = _normalize_key(header)
        if not normalized_header:
            continue
        for field_name, aliases in PARTICIPANT_COLUMN_ALIASES.items():
            if normalized_header in {_normalize_key(alias) for alias in aliases}:
                matched[field_name] = index
                break
    has_name = "full_name" in matched or "first_name" in matched
    has_context = any(field in matched for field in ("company", "position", "participant_type"))
    return matched if has_name and has_context else {}


def load_participants_from_xlsx(file_path: str) -> List[Dict[str, str]]:
    workbook = load_workbook(file_path, data_only=True)
    participants: List[Dict[str, str]] = []

    for sheet in workbook.worksheets:
        header_map: Dict[str, int] = {}
        for row in sheet.iter_rows(values_only=True):
            values = list(row)
            if not any(_safe_text(cell) for cell in values):
                continue
            if not header_map:
                header_map = _match_participant_columns(values)
                continue

            participant: Dict[str, str] = {}
            for field_name, column_index in header_map.items():
                participant[field_name] = _safe_text(values[column_index] if column_index < len(values) else "")

            if not any(participant.values()):
                continue
            participants.append(participant)

    return _normalize_participants(participants)


def _build_attendee_name(participant: Dict[str, Any]) -> str:
    return " ".join(
        part for part in [participant.get("first_name"), participant.get("last_name")] if _safe_text(part)
    ).strip() or "Jan Kowalski"


def _normalize_participants(raw_participants: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    normalized = []
    for participant in raw_participants or []:
        full_name = _first_non_empty(participant.get("full_name"), participant.get("name"))
        split_name = _split_full_name(full_name)
        first_name = _first_non_empty(participant.get("first_name"), split_name["first_name"])
        last_name = _first_non_empty(participant.get("last_name"), split_name["last_name"])
        company = _safe_text(participant.get("company"))
        position = _safe_text(participant.get("position"))
        raw_participant_type = _first_non_empty(
            participant.get("type"),
            participant.get("participant_type"),
            participant.get("role"),
            participant.get("conference_role"),
        )
        if not any([first_name, last_name, company, position, raw_participant_type]):
            continue
        role = _resolve_role_variant(raw_participant_type, position, company)
        normalized.append(
            {
                "type": role["id"],
                "participant_type": role["label"],
                "raw_participant_type": _safe_text(raw_participant_type),
                "first_name": first_name,
                "last_name": last_name,
                "company": company,
                "position": position,
            }
        )
    return normalized


def _build_sample_participant(role_id: str) -> Dict[str, str]:
    return SAMPLE_PARTICIPANTS.get(role_id, SAMPLE_PARTICIPANTS["client"]).copy()


def _build_background_prompt(
    theme_info: Optional[Dict[str, Any]] = None,
    visual_keywords: str = "",
) -> str:
    """Build the image-generation prompt.

    The base is always a dark purple abstract background.  Theme-specific mood
    words and AI-extracted brief keywords are appended so the generated texture
    reinforces the conference's character.
    """
    base = (
        "Abstract background only, portrait orientation, single flat background layer. "
        "Premium corporate-tech aesthetic, minimalist, elegant, restrained. "
        "Deep rich purple and violet tones, dramatic color depth, dark atmosphere. "
        "Sharp geometric accents, crisp edges, controlled contrast, soft atmospheric depth. "
        "Large clean negative space and high readability for future text overlay. "
        "Fully abstract composition, atmospheric but understated, no focal object, no framing device."
    )
    modifiers: List[str] = []
    if theme_info and theme_info.get("prompt_hint"):
        modifiers.append(theme_info["prompt_hint"])
    # Enrich with industry color psychology rationale when available
    if theme_info:
        ind = theme_info.get("industry_colors") or {}
        if ind.get("rationale"):
            modifiers.append(f"color palette inspired by: {ind['rationale']}")
    if visual_keywords:
        modifiers.append(visual_keywords)
    if modifiers:
        return base + " " + ", ".join(modifiers) + "."
    return base


def _build_negative_prompt() -> str:
    return (
        "text, letters, words, typography, numbers, logos, watermark, badge mockup, id card, title bar, "
        "fake ui, document layout, poster layout, presentation slide layout, ghost text, translucent overlay, "
        "duplicate layer, badge frame, placeholder blocks, lower thirds, tables, cards, templates, document chrome"
    )


def _scan_brief_for_visual_keywords(brief: Dict[str, Any], document_brief: Dict[str, Any]) -> str:
    """AI agent that reads the conference brief and returns visual atmosphere
    descriptors to enrich the background image-generation prompt.

    Returns a comma-separated string of descriptors (empty on failure so the
    rest of the pipeline is never blocked).
    """
    brief_summary = {
        "conference_name": _first_non_empty(
            brief.get("product_or_service"), document_brief.get("title")
        ),
        "scope": _safe_text(brief.get("scope_of_work")),
        "target_audience": _safe_text(brief.get("target_audience")),
        "key_messages": _safe_text(brief.get("key_messages")),
        "client_expectations": _safe_text(brief.get("client_expectations")),
        "description": _safe_text(document_brief.get("description")),
        "target_group": _safe_text(document_brief.get("target_group")),
    }

    prompt = (
        "Jesteś art directorem specjalizującym się w brandingu konferencji. "
        "Na podstawie poniższego briefu konferencji wyodrębnij 5–8 zwięzłych deskryptorów wizualnej atmosfery "
        "do abstrakcyjnego obrazu tła. Skup się na nastroju, poziomie energii i metaforach "
        "odzwierciedlających temat konferencji. "
        "Unikaj generycznych słów takich jak 'fioletowy', 'gradient' czy 'abstrakcyjny'. "
        "Zwróć WYŁĄCZNIE listę deskryptorów oddzielonych przecinkami, w języku angielskim "
        "(model generowania obrazów działa najlepiej z angielskimi opisami) — bez wyjaśnień, bez numeracji.\n\n"
        f"Brief konferencji:\n{json.dumps(brief_summary, ensure_ascii=False, indent=2)}"
    )

    try:
        result = extract_structured_text(prompt)
        cleaned = result.strip().strip('"').strip("'")
        return cleaned if cleaned else ""
    except Exception:
        return ""


def _extract_industry_colors(brief: Dict[str, Any], document_brief: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Call GPT-4o acting as a color psychologist to extract industry-appropriate colors.

    The model analyses the conference brief and returns 3 hex colors grounded in
    color-psychology principles for that industry.  Colors are at medium brightness
    so the tone system can darken them (corporate) or brighten them (playful)
    without losing the industry's visual identity.

    Returns a dict with 'primary', 'secondary', 'accent' as (R,G,B) tuples and
    'rationale' as a string, or None on failure.
    """
    brief_summary = {
        "conference_name": _first_non_empty(brief.get("product_or_service"), document_brief.get("title")),
        "industry": _safe_text(brief.get("product_or_service")),
        "scope": _safe_text(brief.get("scope_of_work")),
        "target_audience": _safe_text(brief.get("target_audience")),
        "description": _safe_text(document_brief.get("description")),
        "target_group": _safe_text(document_brief.get("target_group")),
    }

    prompt = (
        "You are a color psychologist specialising in corporate branding and industry color semantics. "
        "Analyse the conference brief below and produce an industry-appropriate colour palette.\n\n"
        "Apply color psychology: consider emotional associations, industry conventions, cultural expectations, "
        "and the psychological impact on the target audience.\n\n"
        "IMPORTANT for gradient_stops: provide 4–5 DIVERSE colors that create a rich, multi-hue gradient "
        "flowing top-to-bottom on the badge background. They should be harmonious but visually varied "
        "(not all the same hue). Use medium brightness — not near-black, not neon.\n\n"
        "Return ONLY a valid JSON object — no markdown fences, no extra text:\n"
        "{\n"
        '  "primary": "#RRGGBB",\n'
        '  "secondary": "#RRGGBB",\n'
        '  "accent": "#RRGGBB",\n'
        '  "gradient_stops": ["#RRGGBB", "#RRGGBB", "#RRGGBB", "#RRGGBB", "#RRGGBB"],\n'
        '  "rationale": "1–2 sentence color psychology explanation"\n'
        "}\n\n"
        f"Conference brief:\n{json.dumps(brief_summary, ensure_ascii=False, indent=2)}"
    )

    try:
        result = extract_structured_text(prompt)
        json_match = re.search(r'\{.*\}', result.strip(), re.DOTALL)
        if not json_match:
            return None
        data = json.loads(json_match.group())
        colors: Dict[str, Any] = {}
        for key in ("primary", "secondary", "accent"):
            val = _safe_text(data.get(key, ""))
            if re.match(r'^#[0-9A-Fa-f]{6}$', val):
                colors[key] = _hex_to_rgb(val)
        if len(colors) >= 2:
            colors["rationale"] = _safe_text(data.get("rationale", ""))
            # Parse multi-stop gradient colours
            raw_stops = data.get("gradient_stops", [])
            if isinstance(raw_stops, list):
                parsed = [
                    _hex_to_rgb(v) for v in raw_stops
                    if isinstance(v, str) and re.match(r'^#[0-9A-Fa-f]{6}$', v.strip())
                ]
                if len(parsed) >= 3:
                    colors["gradient_stops_rgb"] = parsed
            return colors
    except Exception:
        pass
    return None


def _build_badge_layout_data(
    *,
    conference_name: str,
    role_config: Dict[str, str],
    participant_data: Dict[str, str],
) -> Dict[str, Any]:
    full_name = _build_attendee_name(participant_data)
    return {
        "conferenceName": conference_name,
        "participant": {
            "fullName": full_name,
            "firstName": _safe_text(participant_data.get("first_name")),
            "lastName": _safe_text(participant_data.get("last_name")),
            "company": _safe_text(participant_data.get("company")),
            "position": _safe_text(participant_data.get("position")),
            "participantType": role_config["label"],
            "participantTypeId": role_config["id"],
        },
        "branding": {
            "logoAssetPath": LOGO_PATH,
            "brandbookSource": BRAND_GUIDELINES["source_document"],
            "primaryColor": BRAND_GUIDELINES["primary_color"],
            "baseColors": BRAND_GUIDELINES["base_colors"],
            "supportingColors": BRAND_GUIDELINES["supporting_colors"],
            "accentColor": role_config["accent_color"],
            "geometry": BRAND_GUIDELINES["geometry"],
            "motif": BRAND_GUIDELINES["motif"],
            "logoPlacement": BRAND_GUIDELINES["logo_placement"],
            "logoRule": BRAND_GUIDELINES["logo_rule"],
            "fullColorLogoBackgroundRule": BRAND_GUIDELINES["full_color_logo_background_rule"],
        },
        "layout": {
            "badgeSize": {"width": BADGE_SIZE[0], "height": BADGE_SIZE[1]},
            "safeMargin": SAFE_MARGIN,
            "headerHeight": HEADER_HEIGHT,
            "roleStripWidth": ROLE_STRIP_WIDTH,
            "visualCue": role_config["visual_cue"],
            "secondaryText": "",
            "showSecondaryText": False,
            "renderMode": "deterministic_overlay",
        },
    }


def _tone_label(tone: float) -> str:
    """Return a human-readable Polish description of the tone score (post-cap value)."""
    if tone < 0.15:
        return "Bardzo korporacyjny \u2014 zimna, statyczna paleta"
    if tone < 0.30:
        return "Korporacyjny \u2014 stonowane, zimne odcienie"
    if tone < 0.45:
        return "Zr\u00f3wnowa\u017cony \u2014 umiarkowany charakter"
    if tone < 0.60:
        return "Dynamiczny \u2014 cieplejsze akcenty"
    if tone < 0.78:
        return "Swobodny \u2014 \u017cywe, ciep\u0142e barwy"
    return "Bardzo swobodny \u2014 intensywne, gor\u0105ce kolory"


def _build_badge_spec(
    role_config: Dict[str, str],
    conference_name: str,
    participant_data: Optional[Dict[str, str]] = None,
    badge_id: Optional[str] = None,
    badge_name: Optional[str] = None,
    asset_slug: Optional[str] = None,
    theme_info: Optional[Dict[str, Any]] = None,
    visual_keywords: str = "",
) -> Dict[str, Any]:
    resolved_theme = theme_info or _apply_tone_to_theme(CONFERENCE_THEMES["general"], 0.30)
    sample_participant = participant_data or _build_sample_participant(role_config["id"])
    attendee_name = _build_attendee_name(sample_participant)
    tone_value = resolved_theme.get("tone", 0.20)
    return {
        "id": badge_id or f"badge-{role_config['id']}",
        "role_id": role_config["id"],
        "asset_slug": asset_slug or role_config["id"],
        "name": badge_name or f"Badge / {role_config['label']}",
        "conference_name": conference_name,
        "participant_type": role_config["label"],
        "visual_cue": role_config["visual_cue"],
        "accent_color": role_config["accent_color"],
        "sample_participant": sample_participant,
        "headline": _truncate(conference_name, 96),
        "supporting_copy": _truncate(attendee_name or role_config["label"], 96),
        "backgroundPrompt": _build_background_prompt(resolved_theme, visual_keywords),
        "negativePrompt": _build_negative_prompt(),
        "themeInfo": resolved_theme,
        "tone_score": round(tone_value, 2),
        "tone_label": _tone_label(tone_value),
        "badgeLayoutData": _build_badge_layout_data(
            conference_name=conference_name,
            role_config=role_config,
            participant_data=sample_participant,
        ),
        "status": "pending_render",
    }


def build_badge_generation_plan(
    brief: Dict[str, Any],
    document_brief: Dict[str, Any],
    participants: Optional[List[Dict[str, Any]]] = None,
    sources: Optional[List[Dict[str, Any]]] = None,
    image_format: str = "png",
) -> Dict[str, Any]:
    conference_name = _first_non_empty(brief.get("product_or_service"), document_brief.get("title"), fallback="Accenture Conference")

    # ── Detect theme + tone, extract industry colours, then resolve palette ──
    theme_info = _detect_conference_theme(brief, document_brief)
    tone = _detect_tone(brief, document_brief)
    industry_colors = _extract_industry_colors(brief, document_brief)
    theme_info = _apply_tone_to_theme(theme_info, tone, industry_colors)
    visual_keywords = _scan_brief_for_visual_keywords(brief, document_brief)

    role_variants = _extract_role_variants(
        brief.get("scope_of_work"),
        brief.get("target_audience"),
        brief.get("client_expectations"),
        document_brief.get("target_group"),
    )
    role_variants_from_sources = _extract_role_variants_from_sources(sources)
    if role_variants_from_sources:
        merged = {role["id"]: role for role in role_variants}
        for role in role_variants_from_sources:
            merged.setdefault(role["id"], role)
        role_variants = list(merged.values())

    badges = []
    normalized_participants = _normalize_participants(participants)
    if normalized_participants:
        for index, participant in enumerate(normalized_participants, start=1):
            role = ROLE_VARIANT_BY_ID.get(participant["type"], ROLE_VARIANT_BY_ID["guest"])
            attendee_name = _build_attendee_name(participant)
            badges.append(
                _build_badge_spec(
                    role_config=role,
                    conference_name=conference_name,
                    participant_data=participant,
                    badge_id=f"badge-{role['id']}-{index:03d}",
                    badge_name=f"Badge / {attendee_name}",
                    asset_slug=f"{index:03d}-{attendee_name}-{role['id']}",
                    theme_info=theme_info,
                    visual_keywords=visual_keywords,
                )
            )
    else:
        for role in role_variants:
            badges.append(
                _build_badge_spec(
                    role_config=role,
                    conference_name=conference_name,
                    theme_info=theme_info,
                    visual_keywords=visual_keywords,
                )
            )

    return {
        "job_id": uuid.uuid4().hex,
        "status": "started",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "conference_name": conference_name,
        "requested_format": image_format,
        "brandbook": BRAND_GUIDELINES,
        "logo_asset_path": LOGO_PATH,
        "message": "Uruchomiono generowanie graficznych wariantów badge'y zgodnych z briefem i brandbookiem.",
        "summary": {
            "conference_name": conference_name,
            "variants_count": len(badges),
            "participants_count": len(normalized_participants),
            "generation_mode": "participant_list" if normalized_participants else "role_variants",
            "participant_types": sorted({badge["participant_type"] for badge in badges}),
            "brandbook_source": BRAND_GUIDELINES["source_document"],
            "official_logo_applied": True,
            "theme_id": theme_info.get("theme_id", "general"),
            "theme_style": theme_info.get("style", "innovative"),
            "tone_score": round(theme_info.get("tone", 0.30), 2),
            "industry_colors_rationale": (theme_info.get("industry_colors") or {}).get("rationale", ""),
        },
        "badges": badges,
    }


def _write_image_asset(output_dir: str, basename: str, image_bytes: bytes, requested_format: str) -> Dict[str, str]:
    file_extension = _detect_image_extension(image_bytes, fallback=requested_format)
    filename = f"{basename}.{file_extension}"
    file_path = os.path.join(output_dir, filename)
    with open(file_path, "wb") as handle:
        handle.write(image_bytes)
    return {"filename": filename, "file_path": file_path, "format": file_extension}


def _write_badge_batch_zip(output_dir: str, job_id: str, badges: List[Dict[str, Any]]) -> Dict[str, str]:
    zip_filename = f"badge_batch_{job_id}.zip"
    zip_path = os.path.join(output_dir, zip_filename)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for badge in badges:
            file_path = badge.get("file_path")
            filename = badge.get("filename")
            if not file_path or not filename or not os.path.exists(file_path):
                continue
            archive.write(file_path, arcname=filename)

    return {"batch_zip_filename": zip_filename, "batch_zip_path": zip_path}


def start_badge_generation(
    brief: Dict[str, Any],
    document_brief: Dict[str, Any],
    output_dir: str = "generated",
    image_format: str = "png",
    participants: Optional[List[Dict[str, Any]]] = None,
    sources: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    os.makedirs(output_dir, exist_ok=True)
    requested_format = image_format.strip().lower()
    if requested_format not in {"png", "jpg", "jpeg"}:
        raise ValueError("Nieobsługiwany format badge'a. Użyj 'png' albo 'jpg'.")

    plan = build_badge_generation_plan(
        brief=brief,
        document_brief=document_brief,
        participants=participants,
        sources=sources,
        image_format=requested_format,
    )

    generated_count = 0
    failed_count = 0
    background_cache: Dict[str, bytes] = {}
    for badge in plan["badges"]:
        try:
            cache_key = "|".join(
                [
                    _safe_text(badge.get("backgroundPrompt")),
                    _safe_text(badge.get("negativePrompt")),
                ]
            )
            if cache_key not in background_cache:
                background_cache[cache_key] = generate_image_bytes(
                    prompt=badge["backgroundPrompt"],
                    negative_prompt=badge.get("negativePrompt"),
                    size="1024x1024",
                )
            background = background_cache[cache_key]
            composed = _compose_badge_image(badge, background)
            asset = _write_image_asset(
                output_dir=output_dir,
                basename=f"badge_{plan['job_id']}_{_slugify(_safe_text(badge.get('asset_slug')) or badge['id'])}",
                image_bytes=composed,
                requested_format=requested_format,
            )
            badge.update(asset)
            badge["status"] = "generated"
            badge["official_logo_applied"] = True
            badge["brandbook_source"] = BRAND_GUIDELINES["source_document"]
            generated_count += 1
        except Exception as exc:
            badge["status"] = "failed"
            badge["error"] = str(exc)
            failed_count += 1

    if generated_count and not failed_count:
        plan["status"] = "completed"
        if plan["summary"].get("participants_count"):
            plan["message"] = f"Wygenerowano komplet badge'y dla {plan['summary']['participants_count']} uczestników."
        else:
            plan["message"] = "Wygenerowano komplet wariantów badge'y."
    elif generated_count and failed_count:
        plan["status"] = "completed_with_errors"
        plan["message"] = "Część badge'y została wygenerowana, ale wystąpiły błędy dla niektórych wariantów."
    else:
        plan["status"] = "failed"
        plan["message"] = "Nie udało się wygenerować badge'y. Sprawdź konfigurację modelu obrazu lub plik logo."

    plan["completed_at"] = datetime.now(timezone.utc).isoformat()
    plan["summary"]["generated_count"] = generated_count
    plan["summary"]["failed_count"] = failed_count

    manifest_filename = f"badge_generation_{plan['job_id']}.json"
    manifest_path = os.path.join(output_dir, manifest_filename)
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(plan, handle, ensure_ascii=False, indent=2)

    batch_zip = _write_badge_batch_zip(output_dir=output_dir, job_id=plan["job_id"], badges=plan["badges"])
    plan.update(batch_zip)
    plan["file_path"] = manifest_path
    plan["filename"] = manifest_filename
    return plan
