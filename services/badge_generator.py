import io
import json
import os
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from openpyxl import load_workbook

from services.ai_service import generate_image_bytes

BRAND_GUIDELINES = {
    "primary_color": "#4A4AFF",
    "base_colors": ["#000000", "#FFFFFF"],
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

LOGO_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "images", "Accenture-logo.png")
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
        "accent_color": "#D9D9D9",
    },
    {
        "id": "client",
        "label": "Klient",
        "keywords": ["klient", "klienci", "client", "clients"],
        "visual_cue": "szeroki czarny pasek roli i czarny pionowy akcent",
        "accent_color": "#000000",
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
        "label": "Prelegent",
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


def _fit_logo(max_width: int, max_height: int) -> Image.Image:
    if not os.path.exists(LOGO_PATH):
        raise ValueError(
            f"Nie znaleziono pliku logo Accenture pod ścieżką {LOGO_PATH}. "
            "Przywróć plik Accenture-logo.png do katalogu team4/images."
        )
    logo = Image.open(LOGO_PATH).convert("RGBA")
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
            "bar_fill": "#000000",
            "bar_text": "#FFFFFF",
            "bar_border": "#000000",
            "bar_accent": "#000000",
            "edge": "#000000",
        },
        "partner": {
            "bar_fill": "#BAB8B8",
            "bar_text": "#111111",
            "bar_border": "#BAB8B8",
            "bar_accent": "#BAB8B8",
            "edge": "#BAB8B8",
        },
        "speaker": {
            "bar_fill": "#FFFFFF",
            "bar_text": "#111111",
            "bar_border": "#D9D9D9",
            "bar_accent": "#4A4AFF",
            "edge": "#4A4AFF",
        },
        "guest": {
            "bar_fill": "#EFEFEF",
            "bar_text": "#111111",
            "bar_border": "#E2E2E2",
            "bar_accent": "#CFCFCF",
            "edge": "#CFCFCF",
        },
    }
    return styles.get(role_id, styles["guest"])


def _open_generated_background(image_bytes: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return ImageOps.fit(image, BADGE_SIZE, method=Image.Resampling.LANCZOS)


def _compose_badge_image(badge: Dict[str, Any], image_bytes: bytes) -> bytes:
    base = _open_generated_background(image_bytes).filter(ImageFilter.GaussianBlur(radius=8))
    base = Image.blend(
        Image.new("RGB", BADGE_SIZE, _hex_to_rgb("#FCFCFA")),
        base,
        0.3,
    )
    base = ImageEnhance.Color(base).enhance(0.28)
    base = ImageEnhance.Contrast(base).enhance(0.90)
    base = ImageEnhance.Brightness(base).enhance(1.06)
    base = Image.blend(base, Image.new("RGB", BADGE_SIZE, _hex_to_rgb("#FBFBF9")), 0.76)

    canvas = Image.new("RGB", BADGE_SIZE, _hex_to_rgb("#FCFCFA"))
    canvas.paste(base, (0, 0))
    width, height = canvas.size
    overlay = Image.new("RGBA", BADGE_SIZE, (255, 255, 255, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.polygon(
        [
            (0, 0),
            (width * 0.48, 0),
            (width * 0.26, height),
            (0, height),
        ],
        fill=(255, 255, 255, 82),
    )
    overlay_draw.polygon(
        [
            (width * 0.60, 0),
            (width, 0),
            (width, height * 0.58),
            (width * 0.78, height),
            (width * 0.52, height),
        ],
        fill=(161, 0, 255, 18),
    )
    overlay_draw.rectangle((0, 0, width, height), outline=(230, 230, 227, 90), width=2)
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(canvas)

    layout_data = badge.get("badgeLayoutData") or {}
    participant = layout_data.get("participant") or {}
    layout = layout_data.get("layout") or {}
    attendee_name = _safe_text(participant.get("fullName")) or " ".join(
        part for part in [participant.get("firstName"), participant.get("lastName")] if _safe_text(part)
    ).strip() or "Jan Kowalski"
    conference_name = _safe_text(layout_data.get("conferenceName")) or _safe_text(badge.get("conference_name")) or _safe_text(badge.get("headline"))
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
    card_radius = 0
    edge_width = 28
    # draw.rounded_rectangle(
    #     (card_left, card_top, card_right, card_bottom),
    #     radius=card_radius,
    #     fill=_hex_to_rgb("#FEFEFD"),
    #     outline=_hex_to_rgb("#ECECE8"),
    #     width=1,
    # )

    edge_color = _hex_to_rgb(role_style["edge"])
    draw.rectangle(
        (card_right - edge_width, card_top, card_right, card_bottom),
        fill=edge_color,
    )

    title_font = _load_font(42, bold=False)
    role_font = _load_font(48, bold=True)
    company_font = _load_font(48, bold=True)
    position_font = _load_font(42, bold=False)
    secondary_font = _load_font(30, bold=False)
    logo = _fit_logo(max_width=480, max_height=180)

    content_left = card_left + 72
    content_right = card_right - edge_width - 64
    content_width = content_right - content_left
    center_x = (content_left + content_right) // 2

    conference_fill = _hex_to_rgb("#5D347B")
    title_lines = _wrap_text(_truncate(conference_name, 80), draw, title_font, content_width)
    current_y = card_top + 86
    for line in title_lines[:2]:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        line_width = bbox[2] - bbox[0]
        line_height = bbox[3] - bbox[1]
        draw.text(
            (center_x - (line_width // 2), current_y),
            line,
            font=title_font,
            fill=conference_fill,
        )
        current_y += line_height + 4

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
        fill=_hex_to_rgb("#0B0B0B"),
        line_spacing=10,
    )

    separator_y = name_bottom + 42
    separator_half_width = min(220, content_width // 2 - 20)
    draw.line(
        (center_x - separator_half_width, separator_y, center_x + separator_half_width, separator_y),
        fill=_hex_to_rgb("#AFAFAC"),
        width=2,
    )

    info_y = separator_y + 30
    if company_text:
        company_bbox = draw.textbbox((0, 0), company_text, font=company_font)
        company_width = company_bbox[2] - company_bbox[0]
        draw.text(
            (center_x - (company_width // 2), info_y),
            company_text,
            font=company_font,
            fill=_hex_to_rgb("#1D1D1B"),
        )
        info_y += (company_bbox[3] - company_bbox[1]) + 10

    if position_text:
        position_bbox = draw.textbbox((0, 0), position_text, font=position_font)
        position_width = position_bbox[2] - position_bbox[0]
        draw.text(
            (center_x - (position_width // 2), info_y),
            position_text,
            font=position_font,
            fill=_hex_to_rgb("#3A3A37"),
        )
        info_y += (position_bbox[3] - position_bbox[1]) + 8

    if show_secondary_text:
        secondary_bbox = draw.textbbox((0, 0), secondary_text, font=secondary_font)
        secondary_width = secondary_bbox[2] - secondary_bbox[0]
        draw.text(
            (center_x - (secondary_width // 2), info_y + 4),
            secondary_text,
            font=secondary_font,
            fill=_hex_to_rgb("#5C5C58"),
        )

    role_bar_height = 112
    role_bar_left = card_left
    role_bar_right = card_right - edge_width
    role_bar_top = card_bottom - 380
    role_bar_bottom = role_bar_top + role_bar_height
    draw.rectangle(
        (role_bar_left, role_bar_top, role_bar_right, role_bar_bottom),
        fill=_hex_to_rgb(role_style["bar_fill"]),
        outline=_hex_to_rgb(role_style["bar_border"]),
        width=2,
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

    logo_x = center_x - (logo.width // 2)
    logo_y = role_bar_bottom + (card_bottom - role_bar_bottom -logo.height) // 2
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


def _build_background_prompt() -> str:
    return (
        "Abstract background only, portrait orientation, single flat background layer. "
        "Premium corporate-tech aesthetic, minimalist, elegant, restrained. "
        "Palette limited to charcoal, near-black, white, and soft gray with a very subtle purple accent. "
        "Sharp geometric accents, crisp edges, controlled contrast, soft depth only if needed. "
        "Large clean negative space and high readability for future text overlay. "
        "Fully abstract composition, atmospheric but understated, no focal object, no framing device."
    )


def _build_negative_prompt() -> str:
    return (
        "text, letters, words, typography, numbers, logos, watermark, badge mockup, id card, title bar, "
        "fake ui, document layout, poster layout, presentation slide layout, ghost text, translucent overlay, "
        "duplicate layer, badge frame, placeholder blocks, lower thirds, tables, cards, templates, document chrome"
    )


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


def _build_badge_spec(
    role_config: Dict[str, str],
    conference_name: str,
    participant_data: Optional[Dict[str, str]] = None,
    badge_id: Optional[str] = None,
    badge_name: Optional[str] = None,
    asset_slug: Optional[str] = None,
) -> Dict[str, Any]:
    sample_participant = participant_data or _build_sample_participant(role_config["id"])
    attendee_name = _build_attendee_name(sample_participant)
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
        "backgroundPrompt": _build_background_prompt(),
        "negativePrompt": _build_negative_prompt(),
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
                )
            )
    else:
        for role in role_variants:
            badges.append(
                _build_badge_spec(
                    role_config=role,
                    conference_name=conference_name,
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

    plan["file_path"] = manifest_path
    plan["filename"] = manifest_filename
    return plan
