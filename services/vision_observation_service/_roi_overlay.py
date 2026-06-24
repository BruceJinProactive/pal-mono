from __future__ import annotations

import math
from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

from utils.log import logger

_ROI_LABEL_COLORS = (
    (45, 116, 196),
    (36, 132, 96),
    (155, 103, 26),
    (121, 88, 166),
    (170, 74, 85),
)
_MIN_ROI_LABEL_FONT_SIZE = 12
_MAX_ROI_LABEL_FONT_SIZE = 72


def roi_hint_value(roi_hint: dict[str, object], key: str) -> float | None:
    value = roi_hint.get(key)
    if value is None and key == "width":
        value = roi_hint.get("w")
    if value is None and key == "height":
        value = roi_hint.get("h")
    if value is None:
        return None
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def roi_hint_to_image_box(
    roi_hint: dict[str, object] | None,
    image_width: int,
    image_height: int,
) -> tuple[int, int, int, int] | None:
    if not roi_hint:
        return None

    x = roi_hint_value(roi_hint, "x")
    y = roi_hint_value(roi_hint, "y")
    width = roi_hint_value(roi_hint, "width")
    height = roi_hint_value(roi_hint, "height")
    if x is None or y is None or width is None or height is None:
        return None
    if width <= 0 or height <= 0:
        return None

    values = (x, y, width, height)
    if all(0 <= value <= 1 for value in values):
        x1 = round(x * image_width)
        y1 = round(y * image_height)
        x2 = round((x + width) * image_width)
        y2 = round((y + height) * image_height)
    else:
        x1 = round((x / 1000) * image_width)
        y1 = round((y / 1000) * image_height)
        x2 = round(((x + width) / 1000) * image_width)
        y2 = round(((y + height) / 1000) * image_height)

    x1 = max(0, min(image_width - 1, x1))
    y1 = max(0, min(image_height - 1, y1))
    x2 = max(0, min(image_width - 1, x2))
    y2 = max(0, min(image_height - 1, y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return (x1, y1, x2, y2)


def roi_label_font_size(image_width: int, image_height: int) -> int:
    return max(
        _MIN_ROI_LABEL_FONT_SIZE,
        min(
            _MAX_ROI_LABEL_FONT_SIZE,
            round(max(image_width, image_height) / 80),
        ),
    )


def _roi_label_font(
    image_width: int,
    image_height: int,
) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    font_size = roi_label_font_size(image_width, image_height)
    for font_name in ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(font_name, font_size)
        except OSError:
            continue

    try:
        return ImageFont.load_default(size=font_size)
    except TypeError:
        return ImageFont.load_default()


def draw_roi_labels_on_image_bytes(
    image_bytes: bytes,
    entities_with_states: list[dict[str, Any]],
    image_label: str,
) -> bytes:
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            pil_image = ImageOps.exif_transpose(image).convert("RGB")
            image_width, image_height = pil_image.size

            labeled_boxes: list[tuple[str, tuple[int, int, int, int]]] = []
            for entity_info in entities_with_states:
                box = roi_hint_to_image_box(
                    entity_info.get("roi_hint"), image_width, image_height
                )
                name = entity_info.get("name")
                if box is not None and name:
                    labeled_boxes.append((str(name), box))

            if not labeled_boxes:
                return image_bytes

            draw = ImageDraw.Draw(pil_image)
            font = _roi_label_font(image_width, image_height)
            font_size = roi_label_font_size(image_width, image_height)
            line_width = max(2, round(max(image_width, image_height) / 400))
            padding = max(2, round(font_size * 0.25), line_width)

            for index, (label, box) in enumerate(labeled_boxes):
                color = _ROI_LABEL_COLORS[index % len(_ROI_LABEL_COLORS)]
                x1, y1, x2, y2 = box
                draw.rectangle((x1, y1, x2, y2), outline=color, width=line_width)

                text_bbox = draw.textbbox((0, 0), label, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                label_width = text_width + padding * 2
                label_height = text_height + padding * 2
                label_x = min(x1, max(0, image_width - label_width))
                label_y = y1 - label_height
                if label_y < 0:
                    label_y = min(
                        y1 + line_width,
                        max(0, image_height - label_height),
                    )
                label_y = max(0, label_y)

                draw.rectangle(
                    (
                        label_x,
                        label_y,
                        label_x + label_width,
                        label_y + label_height,
                    ),
                    fill=color,
                )
                draw.text(
                    (label_x + padding, label_y + padding),
                    label,
                    fill=(255, 255, 255),
                    font=font,
                )

            buffer = BytesIO()
            pil_image.save(buffer, format="JPEG", quality=90)
            return buffer.getvalue()
    except (OSError, TypeError, ValueError, OverflowError) as e:
        logger.warning(
            f"[Vision Observation] Failed to draw ROI labels on {image_label}: {e}"
        )
        return image_bytes
