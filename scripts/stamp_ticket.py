import os
import glob
import logging
import stat
import time
from PIL import Image, ImageDraw, ImageFont

# Project base (scripts/ is one level below project root)
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "ticket_image")
DEFAULT_OUT_DIR = os.path.join(BASE_DIR, "ticket_output")

# Visual defaults (tweak as needed)
QR_SCALE = 0.30            # fraction of template width for QR width
QR_MARGIN = 24             # px margin when using margin placement
TEXT_MAX_WIDTH_RATIO = 0.85
TEXT_SIZE_DP = 60
FONT_PATHS = [
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/Calibri.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
]

# Anchor defaults (0..1)
QR_ANCHOR_X_PCT = 0.5
QR_ANCHOR_Y_PCT = 0.73
OFFSET_X_PX = 0
OFFSET_Y_PX = 0

# Team name placement
TEAM_NAME_Y_PCT = 0.43
TEAM_NAME_OFFSET_PX = 0

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def find_font(size):
    for p in FONT_PATHS:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()

def pick_template(template_dir=None):
    """
    Return a template file path. Searches TEMPLATE_DIR by default.
    """
    td = template_dir or TEMPLATE_DIR
    logger.debug("pick_template: looking in %s", td)
    files = glob.glob(os.path.join(td, "*.*")) if os.path.isdir(td) else []
    if not files:
        raise FileNotFoundError(f"No template found in {td}")
    # prefer png/jpg
    for ext in (".png", ".jpg", ".jpeg"):
        for f in files:
            if f.lower().endswith(ext):
                logger.debug("pick_template: selected %s", f)
                return f
    logger.debug("pick_template: fallback selected %s", files[0])
    return files[0]

def _safe_save_image(img, out_path, attempts=5):
    """
    Save image to a temp file then atomically replace target (safer when OneDrive/locks present).
    """
    tmp_path = out_path + ".tmp"
    out_dir = os.path.dirname(out_path)
    os.makedirs(out_dir, exist_ok=True)
    for attempt in range(1, attempts + 1):
        try:
            img.save(tmp_path)
            os.replace(tmp_path, out_path)
            logger.info("Saved composed image to %s", out_path)
            return out_path
        except PermissionError:
            logger.warning("PermissionError saving %s (attempt %d/%d)", out_path, attempt, attempts)
            try:
                if os.path.exists(out_path):
                    os.chmod(out_path, stat.S_IREAD | stat.S_IWRITE)
            except Exception:
                pass
            time.sleep(0.4 * attempt)
        except Exception:
            # cleanup tmp then re-raise
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            raise
    raise PermissionError(f"Could not write file {out_path} after {attempts} attempts")

def compose_ticket(template_path, qr_path, team_name, out_path,
                   qr_scale=None,
                   qr_anchor_x_pct=None, qr_anchor_y_pct=None,
                   offset_x_px=0, offset_y_px=0, qr_margin_px=None):
    """
    Paste QR onto template and draw team name.
    Signature is intentionally compatible with dashboard.py dynamic calls.
    """
    logger.debug("compose_ticket: template=%s qr=%s team='%s' out=%s", template_path, qr_path, team_name, out_path)
    qr_scale = qr_scale if qr_scale is not None else QR_SCALE

    tpl = Image.open(template_path).convert("RGBA")
    qr = Image.open(qr_path).convert("RGBA")
    tw, th = tpl.size
    logger.debug("compose_ticket: template size %dx%d", tw, th)

    qr_w = int(tw * qr_scale)
    qr_h = qr_w
    logger.debug("compose_ticket: resizing QR to %dx%d", qr_w, qr_h)
    qr_resized = qr.resize((qr_w, qr_h), Image.LANCZOS)

    # placement
    if qr_anchor_x_pct is not None and qr_anchor_y_pct is not None:
        paste_x = int(tw * qr_anchor_x_pct) - (qr_w // 2) + int(offset_x_px)
        paste_y = int(th * qr_anchor_y_pct) - (qr_h // 2) + int(offset_y_px)
        logger.debug("compose_ticket: anchor placement anchor=(%.3f,%.3f) offset=(%d,%d) -> paste=(%d,%d)",
                     qr_anchor_x_pct, qr_anchor_y_pct, offset_x_px, offset_y_px, paste_x, paste_y)
    else:
        margin = QR_MARGIN if qr_margin_px is None else qr_margin_px
        paste_x = tw - qr_w - margin + int(offset_x_px)
        paste_y = th - qr_h - margin + int(offset_y_px)
        logger.debug("compose_ticket: margin placement margin=%d offset=(%d,%d) -> paste=(%d,%d)",
                     margin, offset_x_px, offset_y_px, paste_x, paste_y)

    # enforce bounds
    paste_x = max(0, min(paste_x, tw - qr_w))
    paste_y = max(0, min(paste_y, th - qr_h))
    logger.debug("compose_ticket: final paste coords (%d,%d)", paste_x, paste_y)

    composed = tpl.copy()
    composed.paste(qr_resized, (paste_x, paste_y), qr_resized)

    # draw team name (ALL CAPS)
    draw = ImageDraw.Draw(composed)
    font_size = max(12, int(tw * (TEXT_SIZE_DP / 800)))
    font = find_font(font_size)
    text = (team_name or "").upper()
    max_text_w = int(tw * TEXT_MAX_WIDTH_RATIO)

    # shrink font until fits
    while True:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        if text_w <= max_text_w or font_size <= 10:
            break
        font_size -= 2
        font = find_font(font_size)
    text_x = (tw - text_w) // 2
    text_y = int(th * TEAM_NAME_Y_PCT) + int(TEAM_NAME_OFFSET_PX)
    logger.debug("compose_ticket: drawing text '%s' at (%d,%d) font_size=%d", text, text_x, text_y, font_size)

    # draw thin white outline then black fill for crispness
    outline_color = "white"
    fill_color = "black"
    for ox, oy in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
        draw.text((text_x + ox, text_y + oy), text, font=font, fill=outline_color)
    draw.text((text_x, text_y), text, font=font, fill=fill_color)

    # ensure output dir exists and save safely
    out_dir = os.path.dirname(out_path) or DEFAULT_OUT_DIR
    os.makedirs(out_dir, exist_ok=True)
    composed.convert("RGB").save(out_path, format='PNG')
    logger.info("Saved composed ticket: %s", out_path)
    return out_path

def compose_ticket_for(unique_id, qr_path=None, team_name=None, template_path=None, out_dir=None):
    """
    Convenience helper: choose template, determine out_path and call compose_ticket.
    Returns final out_path.
    """
    tpath = template_path or pick_template()
    odir = out_dir or DEFAULT_OUT_DIR
    os.makedirs(odir, exist_ok=True)
    out_file = os.path.join(odir, f"ticket_{unique_id}.png")
    return compose_ticket(
        tpath,
        qr_path,
        team_name or "",
        out_file,
        qr_anchor_x_pct=QR_ANCHOR_X_PCT,
        qr_anchor_y_pct=QR_ANCHOR_Y_PCT,
        offset_x_px=OFFSET_X_PX,
        offset_y_px=OFFSET_Y_PX,
    )