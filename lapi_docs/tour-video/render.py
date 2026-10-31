"""Render the Lapi tour as a continuous motion video (frames), timed to the recorded narration.

1280x720, 30 fps. One moving background the whole way; each scene's elements ease in and out with
crossfades, so there are no hard cuts. Scene times come from voice.json (the narration's own timing).
"""
import json, math, pathlib, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = pathlib.Path(__file__).parent
FRAMES = HERE / 'frames'; FRAMES.mkdir(exist_ok=True)
W, H, FPS = 1280, 720, 30
PUBLIC = pathlib.Path(r'C:\Users\Laya\Documents\Lapi\lapi_frontend\public')
FONTS = pathlib.Path(r'C:\Windows\Fonts')
voice = json.load(open(HERE / 'voice.json'))
SCENES = {s['id']: s for s in voice['scenes']}
END = voice['scenes'][-1]['end'] + 3.0
TOTAL_FRAMES = int(END * FPS)
ORANGE, INK, BLUE, WHITE = (253, 186, 116), (20, 33, 61), (29, 45, 107), (255, 255, 255)

_fonts = {}
def font(size, bold=False):
    key = (size, bold)
    if key not in _fonts: _fonts[key] = ImageFont.truetype(str(FONTS / ('segoeuib.ttf' if bold else 'segoeui.ttf')), size)
    return _fonts[key]

# ---------------------------------------------------------------- easing and timing
def clamp(x, lo=0.0, hi=1.0): return max(lo, min(hi, x))
def ease_out(x): x = clamp(x); return 1 - (1 - x) ** 3
def ease_in_out(x): x = clamp(x); return 3 * x * x - 2 * x * x * x
def prog(t, start, dur): return clamp((t - start) / dur) if dur > 0 else 1.0
def pop(x):  # overshoot a little, like a card popping in
    x = clamp(x); return 1 + 0.18 * math.sin(x * math.pi) * (1 - x) if x < 1 else 1.0

def scene_alpha(t, sid, fade=0.55, lead=0.35):
    """1 while the scene is spoken, fading in a little before its first word and out as the next starts."""
    s = SCENES[sid]; ids = [x['id'] for x in voice['scenes']]; n = ids.index(sid)
    start = s['start'] - lead
    end = (voice['scenes'][n + 1]['start'] - lead) if n + 1 < len(ids) else END + 1
    return min(ease_in_out(prog(t, start, fade)), 1 - ease_in_out(prog(t, end - fade, fade)))

# ---------------------------------------------------------------- background
def gradient():
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    u = (x / W + y / H) / 2
    c0, c1, c2 = np.array([22, 38, 120]), np.array([88, 60, 170]), np.array([236, 120, 90])
    img = np.where(u[..., None] < 0.55, c0 + (c1 - c0) * (u[..., None] / 0.55), c1 + (c2 - c1) * ((u[..., None] - 0.55) / 0.45))
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), 'RGB')
BG = gradient()

def glow(radius, colour):
    size = radius * 4  # room for the blur, so the glow fades to nothing well inside its box
    g = Image.new('L', (size, size), 0)
    ImageDraw.Draw(g).ellipse((radius, radius, radius * 3, radius * 3), fill=170)
    g = g.filter(ImageFilter.GaussianBlur(radius * 0.6))
    rgba = Image.new('RGBA', (size, size), colour + (0,)); rgba.putalpha(g)
    return rgba
BLOBS = [(glow(260, (120, 140, 255)), 0.11, 0.0), (glow(300, (255, 170, 110)), 0.08, 2.1), (glow(220, (90, 200, 255)), 0.09, 4.2)]

def background(t):
    frame = BG.copy()
    for blob, speed, phase in BLOBS:
        cx = W * (0.5 + 0.42 * math.sin(speed * t + phase)); cy = H * (0.5 + 0.38 * math.cos(speed * 0.8 * t + phase))
        frame.paste(blob, (int(cx - blob.width / 2), int(cy - blob.height / 2)), blob)
    return frame

# ---------------------------------------------------------------- drawing helpers
def layer(): return Image.new('RGBA', (W, H), (0, 0, 0, 0))
def composite(frame, lay, alpha):
    if alpha <= 0: return frame
    if alpha < 1: lay = lay.copy(); lay.putalpha(lay.getchannel('A').point(lambda a: int(a * alpha)))
    return Image.alpha_composite(frame, lay)

def card(d, box, radius=22, fill=(255, 255, 255, 235), outline=None):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2 if outline else 0)

def glass(d, box, radius=18): card(d, box, radius, fill=(255, 255, 255, 36), outline=(255, 255, 255, 70))

def text(d, xy, s, size=24, bold=False, fill=WHITE, anchor='la'):
    d.text(xy, s, font=font(size, bold), fill=fill, anchor=anchor)

def check(d, cx, cy, colour, size=9, width=3):
    d.line((cx - size, cy, cx - size * 0.3, cy + size * 0.7, cx + size, cy - size * 0.7), fill=colour, width=width, joint='curve')

def chip(d, x, y, s, fill=(238, 242, 251, 255), ink=INK, size=18):
    w = font(size, True).getlength(s) + 26
    card(d, (x, y, x + w, y + 34), radius=17, fill=fill)
    text(d, (x + 13, y + 7), s, size, True, ink)
    return w

LOGO = Image.open(PUBLIC / 'lapi-mark-512.png').convert('RGBA')
def logo(lay, cx, cy, size):
    img = LOGO.resize((size, size), Image.LANCZOS)
    lay.paste(img, (int(cx - size / 2), int(cy - size / 2)), img)

def icon(d, kind, cx, cy, colour=(29, 45, 107, 255)):
    """Simple line icons for the source tiles."""
    s = 11
    if kind == 'Documents': d.rectangle((cx - s, cy - s - 2, cx + s - 4, cy + s + 2), outline=colour, width=3); d.line((cx - s + 4, cy - 2, cx + s - 8, cy - 2), fill=colour, width=3); d.line((cx - s + 4, cy + 5, cx + s - 8, cy + 5), fill=colour, width=3)
    elif kind == 'Databases': d.ellipse((cx - s, cy - s - 3, cx + s, cy - s + 5), outline=colour, width=3); d.line((cx - s, cy - s + 1, cx - s, cy + s - 3), fill=colour, width=3); d.line((cx + s, cy - s + 1, cx + s, cy + s - 3), fill=colour, width=3); d.arc((cx - s, cy + s - 7, cx + s, cy + s + 1), 0, 180, fill=colour, width=3)
    elif kind == 'Cloud storage': d.ellipse((cx - s - 2, cy - 2, cx + 2, cy + 10), outline=colour, width=3); d.ellipse((cx - 4, cy - 10, cx + s + 2, cy + 10), outline=colour, width=3)
    elif kind == 'Apps & APIs': d.line((cx - 3, cy - s, cx - s, cy, cx - 3, cy + s), fill=colour, width=3); d.line((cx + 3, cy - s, cx + s, cy, cx + 3, cy + s), fill=colour, width=3)
    elif kind == 'Sheets': d.rectangle((cx - s, cy - s + 2, cx + s, cy + s - 2), outline=colour, width=3); d.line((cx - s, cy, cx + s, cy), fill=colour, width=2); d.line((cx - 2, cy - s + 2, cx - 2, cy + s - 2), fill=colour, width=2)
    elif kind == 'Email': d.rectangle((cx - s - 1, cy - s + 3, cx + s + 1, cy + s - 3), outline=colour, width=3); d.line((cx - s - 1, cy - s + 3, cx, cy + 1, cx + s + 1, cy - s + 3), fill=colour, width=3)
    elif kind == 'Photo': d.rectangle((cx - s - 1, cy - s + 4, cx + s + 1, cy + s - 2), outline=colour, width=3); d.ellipse((cx - 5, cy - 4, cx + 5, cy + 6), outline=colour, width=3)

def subtitle(frame, t):
    """The sentence being spoken, as a soft caption bar (accessible, and good for sharing without sound)."""
    current = next((s for s in voice['scenes'] if s['start'] - 0.2 <= t <= s['end'] + 0.4), None)
    if not current: return frame
    lay = layer(); d = ImageDraw.Draw(lay)
    words = current['text'].split(); lines, line = [], ''
    for w in words:
        if font(26).getlength(line + ' ' + w) > W - 260: lines.append(line.strip()); line = w
        else: line += ' ' + w
    lines.append(line.strip())
    y0 = H - 40 - 36 * len(lines)
    for i, s in enumerate(lines):
        tw = font(26).getlength(s)
        card(d, (W / 2 - tw / 2 - 16, y0 + i * 36 - 4, W / 2 + tw / 2 + 16, y0 + i * 36 + 32), radius=10, fill=(10, 18, 50, 150))
        text(d, (W / 2, y0 + i * 36 + 14), s, 26, False, WHITE, 'mm')
    return Image.alpha_composite(frame, lay)

# ---------------------------------------------------------------- scenes
SOURCES = ['Documents', 'Databases', 'Cloud storage', 'Apps & APIs', 'Sheets', 'Email']

def scene_welcome(t):
    s = SCENES['welcome']['start']; lay = layer(); d = ImageDraw.Draw(lay)
    k = ease_out(prog(t, s, 0.9))
    logo(lay, W / 2, 250 - 20 * (1 - k), int(150 * pop(prog(t, s, 0.9))))
    words = [('Connect.', WHITE), ('Unify.', (200, 214, 255)), ('Ask.', ORANGE)]
    x = W / 2 - 300
    for i, (w, c) in enumerate(words):
        a = ease_out(prog(t, s + 1.3 + i * 0.75, 0.6))
        if a > 0:
            sub = layer(); ImageDraw.Draw(sub).text((x, 360 + 18 * (1 - a)), w, font=font(74, True), fill=c + (int(255 * a),))
            lay = Image.alpha_composite(lay, sub)
        x += font(74, True).getlength(w) + 26
    d = ImageDraw.Draw(lay)
    a = ease_out(prog(t, s + 3.6, 0.8))
    if a > 0: text(d, (W / 2, 470), 'Documents · Spreadsheets · Databases · Apps  →  one knowledge base', 26, False, WHITE + (int(235 * a),), 'mm')
    return lay

def tile_box(i, x0=120, y0=150):
    return (x0, y0 + i * 72, x0 + 300, y0 + i * 72 + 58)

def scene_connect(t):
    s = SCENES['connect']['start']; lay = layer(); d = ImageDraw.Draw(lay)
    text(d, (120, 90), 'Add knowledge', 34, True, WHITE)
    for i, name in enumerate(SOURCES):
        a = ease_out(prog(t, s + 0.2 + i * 0.28, 0.6))
        if a <= 0: continue
        x0, y0, x1, y1 = tile_box(i); dx = -260 * (1 - a)
        glass(d, (x0 + dx, y0, x1 + dx, y1))
        d.ellipse((x0 + dx + 14, y0 + 10, x0 + dx + 52, y0 + 48), fill=(255, 255, 255, 255)); icon(d, name, x0 + dx + 33, y0 + 29)
        text(d, (x0 + dx + 66, y0 + 29), name, 23, True, WHITE, 'lm')
    # A phone taking a photo, and the step-by-step guide card.
    a = ease_out(prog(t, s + 2.4, 0.8))
    if a > 0:
        px, py = 560, 170 + 30 * (1 - a)
        card(d, (px, py, px + 150, py + 290), radius=26, fill=(20, 33, 61, int(235 * a)), outline=(255, 255, 255, int(120 * a)))
        d.rounded_rectangle((px + 14, py + 40, px + 136, py + 250), radius=10, fill=(255, 255, 255, int(230 * a)))
        d.rectangle((px + 30, py + 60, px + 120, py + 180), outline=(29, 45, 107, int(255 * a)), width=3)
        for j in range(4): d.line((px + 40, py + 80 + j * 24, px + 110, py + 80 + j * 24), fill=(120, 130, 160, int(255 * a)), width=3)
        d.ellipse((px + 60, py + 200, px + 90, py + 230), fill=(253, 186, 116, int(255 * a)))
        text(d, (px + 75, py + 272), 'Snap a photo', 16, True, (255, 255, 255, int(255 * a)), 'mm')
    a = ease_out(prog(t, s + 4.6, 0.8))
    if a > 0:
        gx, gy = 780, 170 + 30 * (1 - a)
        card(d, (gx, gy, gx + 380, gy + 290), fill=(255, 255, 255, int(240 * a)))
        text(d, (gx + 24, gy + 24), 'Connect Google Drive', 24, True, INK + (int(255 * a),))
        text(d, (gx + 24, gy + 58), 'Step-by-step guide', 17, False, (90, 100, 130, int(255 * a)))
        for j, step in enumerate(['Sign in with your work account', 'Choose the folders to read', 'Pick which dataset receives them']):
            b = ease_out(prog(t, s + 5.2 + j * 0.55, 0.5))
            if b <= 0: continue
            cy = gy + 110 + j * 52
            d.ellipse((gx + 24, cy - 14, gx + 52, cy + 14), fill=(253, 186, 116, int(255 * a * b)))
            text(d, (gx + 38, cy), str(j + 1), 17, True, INK + (int(255 * a * b),), 'mm')
            text(d, (gx + 66, cy), step, 19, False, INK + (int(255 * a * b),), 'lm')
    return lay

def bezier(p0, p1, p2, p3, u):
    return tuple((1 - u) ** 3 * p0[i] + 3 * (1 - u) ** 2 * u * p1[i] + 3 * (1 - u) * u * u * p2[i] + u ** 3 * p3[i] for i in range(2))

def scene_unify(t):
    s = SCENES['unify']['start']; lay = layer(); d = ImageDraw.Draw(lay)
    cx, cy = 760, 360
    # Tiles slide to the left column and send their content along curves into the knowledge base.
    for i, name in enumerate(SOURCES):
        x0, y0, x1, y1 = tile_box(i, 90, 130)
        glass(d, (x0, y0, x1, y1)); d.ellipse((x0 + 14, y0 + 10, x0 + 52, y0 + 48), fill=WHITE + (255,)); icon(d, name, x0 + 33, y0 + 29)
        text(d, (x0 + 66, y0 + 29), name, 21, True, WHITE, 'lm')
        p0 = (x1, (y0 + y1) / 2); p3 = (cx - 150, cy); p1 = (p0[0] + 120, p0[1]); p2 = (p3[0] - 120, p3[1])
        k = ease_in_out(prog(t, s + 0.3 + i * 0.15, 1.6))
        pts = [bezier(p0, p1, p2, p3, u * k) for u in np.linspace(0, 1, 40)]
        if k > 0: d.line(pts, fill=(255, 255, 255, 110), width=3)
        for m in range(3):  # travelling dots
            u = ((t - s) * 0.45 + m / 3 + i * 0.11) % 1.0
            if k >= 1 or u < k:
                x, y = bezier(p0, p1, p2, p3, u); d.ellipse((x - 6, y - 6, x + 6, y + 6), fill=ORANGE + (255,))
    k = pop(prog(t, s, 1.0)); r = int(118 * k)
    d.ellipse((cx - r - 36, cy - r - 36, cx + r + 36, cy + r + 36), fill=(255, 255, 255, 30))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=WHITE + (255,))
    for i in range(16):
        a = (i / 16) * math.pi * 2 + (t - s) * 0.35; rr = r + 26
        d.ellipse((cx + math.cos(a) * rr - 4, cy + math.sin(a) * rr - 4, cx + math.cos(a) * rr + 4, cy + math.sin(a) * rr + 4), fill=(ORANGE if i % 4 == 0 else (220, 228, 255)) + (255,))
    if r > 10: logo(lay, cx, cy, int(r * 1.05))
    d = ImageDraw.Draw(lay)
    text(d, (cx, cy + 175), 'One knowledge base', 30, True, WHITE, 'mm')
    text(d, (cx, cy + 212), 'every page read · even scans and photos · indexed with your models', 19, False, (220, 228, 255, 255), 'mm')
    a = ease_out(prog(t, s + 3.0, 0.7))
    if a > 0:
        chip(d, cx + 180, cy - 150, 'Datasets: Contracts · Invoices · HR', fill=(255, 255, 255, int(235 * a)))
    return lay

ANSWER = ['Three contracts moved to net-60 payment terms', 'this quarter: Acme, Birch and Corvid.']
def scene_ask(t):
    s = SCENES['ask']['start']; lay = layer(); d = ImageDraw.Draw(lay)
    a = ease_out(prog(t, s, 0.8)); x0 = 290 + 240 * (1 - a); y0 = 110
    card(d, (x0, y0, x0 + 700, y0 + 460), radius=26, fill=(255, 255, 255, int(245 * a)))
    d.rounded_rectangle((x0, y0, x0 + 700, y0 + 66), radius=26, fill=(20, 33, 61, int(255 * a))); d.rectangle((x0, y0 + 40, x0 + 700, y0 + 66), fill=(20, 33, 61, int(255 * a)))
    logo(lay, x0 + 36, y0 + 33, 40); d = ImageDraw.Draw(lay)
    text(d, (x0 + 66, y0 + 24), 'Lapi Agent', 22, True, (255, 255, 255, int(255 * a)), 'lm')
    text(d, (x0 + 66, y0 + 48), 'answers with sources', 15, False, (200, 214, 255, int(255 * a)), 'lm')
    q = 'What changed in renewals?'; n = int(len(q) * ease_out(prog(t, s + 0.6, 1.2)))
    if n:
        qw = font(22, True).getlength(q[:n]) + 36
        card(d, (x0 + 660 - qw, y0 + 90, x0 + 660, y0 + 134), radius=18, fill=(29, 45, 107, int(255 * a)))
        text(d, (x0 + 642, y0 + 112), q[:n], 22, True, (255, 255, 255, int(255 * a)), 'rm')
    b = ease_out(prog(t, s + 2.3, 0.9))
    if b > 0:
        card(d, (x0 + 40, y0 + 160, x0 + 660, y0 + 260), radius=14, fill=(245, 247, 252, int(255 * a * b)))
        d.rectangle((x0 + 40, y0 + 160, x0 + 46, y0 + 260), fill=(253, 186, 116, int(255 * a * b)))
        for i, line in enumerate(ANSWER):
            text(d, (x0 + 64, y0 + 186 + i * 34), line, 22, False, INK + (int(255 * a * b),), 'lm')
        for i in range(3):
            cx = x0 + 560 + i * 30; d.ellipse((cx - 11, y0 + 230, cx + 11, y0 + 252), fill=(255, 237, 213, int(255 * a * b))); text(d, (cx, y0 + 241), str(i + 1), 14, True, (154, 52, 18, int(255 * a * b)), 'mm')
    c = ease_out(prog(t, s + 3.4, 0.8))
    if c > 0:
        text(d, (x0 + 40, y0 + 292), 'SOURCES', 14, True, (90, 100, 130, int(255 * a * c)))
        x = x0 + 40
        for i, src in enumerate(['Contracts.pdf', 'CRM', 'Drive']):
            e = ease_out(prog(t, s + 3.6 + i * 0.3, 0.5)); x += chip(d, x, y0 + 318, f'{i + 1}  {src}', fill=(238, 242, 251, int(255 * a * e))) + 12
        e = ease_out(prog(t, s + 4.7, 0.6))
        if e > 0: check(d, x0 + 52, y0 + 390, (22, 101, 52, int(255 * a * e))); text(d, (x0 + 72, y0 + 380), 'Verified against your data', 20, True, (22, 101, 52, int(255 * a * e)))
    return lay

FIELDS = [('Supplier', 'Acme Ltd'), ('Invoice number', 'INV-2041'), ('Due date', '30 Nov 2026'), ('Total', '€ 12,480.00')]
def scene_extract(t):
    s = SCENES['extract']['start']; lay = layer(); d = ImageDraw.Draw(lay)
    a = ease_out(prog(t, s, 0.8))
    # Document on the left with highlight boxes; values on the right.
    dx, dy = 180 + 60 * (1 - a), 110
    card(d, (dx, dy, dx + 360, dy + 470), radius=14, fill=(255, 255, 255, int(245 * a)))
    text(d, (dx + 28, dy + 30), 'INVOICE', 22, True, INK + (int(255 * a),))
    for j in range(12): d.line((dx + 28, dy + 80 + j * 30, dx + 330 - (j % 3) * 60, dy + 80 + j * 30), fill=(205, 212, 230, int(255 * a)), width=5)
    rx, ry = 620 + 60 * (1 - a), 110
    card(d, (rx, ry, rx + 480, ry + 470), radius=22, fill=(255, 255, 255, int(245 * a)))
    text(d, (rx + 28, ry + 26), 'Review side by side', 24, True, INK + (int(255 * a),))
    text(d, (rx + 28, ry + 60), 'Lapi suggested these fields', 17, False, (90, 100, 130, int(255 * a)))
    for i, (f, v) in enumerate(FIELDS):
        b = ease_out(prog(t, s + 1.2 + i * 0.75, 0.6))
        if b <= 0: continue
        y = ry + 110 + i * 78
        card(d, (rx + 28, y, rx + 452, y + 62), radius=12, fill=(245, 247, 252, int(255 * a * b)))
        text(d, (rx + 46, y + 20), f, 16, True, (90, 100, 130, int(255 * a * b)), 'lm')
        text(d, (rx + 46, y + 44), v, 21, True, INK + (int(255 * a * b),), 'lm')
        d.ellipse((rx + 400, y + 17, rx + 428, y + 45), fill=(22, 101, 52, int(255 * a * b))); check(d, rx + 414, y + 31, (255, 255, 255, int(255 * a * b)), size=7)
        hy = dy + 80 + (2 + i * 3) * 30
        d.rectangle((dx + 24, hy - 12, dx + 220, hy + 12), outline=(253, 150, 60, int(255 * a * b)), width=3)
        d.line((dx + 222, hy, rx + 28, y + 31), fill=(253, 150, 60, int(140 * a * b)), width=2)
    return lay

SKILL_LINES = ['name: invoice-review', 'document_types: invoice, bill', 'keywords: overdue, duplicate', '---', '1. Total by supplier.', '2. Flag duplicates and late ones.']
def scene_skills(t):
    s = SCENES['skills']['start']; lay = layer(); d = ImageDraw.Draw(lay)
    a = ease_out(prog(t, s, 0.8)); fx, fy = 150 + 60 * (1 - a), 120
    card(d, (fx, fy, fx + 470, fy + 420), radius=22, fill=(255, 255, 255, int(245 * a)))
    text(d, (fx + 28, fy + 24), 'SKILL.md', 22, True, INK + (int(255 * a),)); text(d, (fx + 28, fy + 54), 'a short playbook, uploaded once', 16, False, (90, 100, 130, int(255 * a)))
    for i, line in enumerate(SKILL_LINES):
        n = int(len(line) * ease_out(prog(t, s + 0.5 + i * 0.55, 0.5)))
        if n: text(d, (fx + 28, fy + 110 + i * 42), line[:n], 22, True, (29, 45, 107, int(255 * a)) if i < 3 else INK + (int(255 * a),))
    b = ease_out(prog(t, s + 4.0, 0.8))
    if b > 0:
        cx, cy = 700 + 60 * (1 - b), 170
        card(d, (cx, cy, cx + 430, cy + 300), radius=22, fill=(255, 255, 255, int(245 * b)))
        logo(lay, cx + 34, cy + 32, 34); d = ImageDraw.Draw(lay)
        text(d, (cx + 60, cy + 22), 'Lapi Agent', 20, True, INK + (int(255 * b),))
        card(d, (cx + 24, cy + 70, cx + 406, cy + 112), radius=14, fill=(238, 242, 251, int(255 * b)))
        text(d, (cx + 40, cy + 91), 'Which invoices are overdue?', 20, True, INK + (int(255 * b),), 'lm')
        c = ease_out(prog(t, s + 5.0, 0.5))
        if c > 0:
            w = chip(d, cx + 24, cy + 132, 'Using skill: invoice-review', fill=(255, 243, 224, int(255 * c)), ink=(154, 52, 18), size=17)
        e = ease_out(prog(t, s + 5.7, 0.6))
        if e > 0:
            text(d, (cx + 24, cy + 190), '3 overdue, 1 duplicate.', 21, False, INK + (int(255 * e),))
            text(d, (cx + 24, cy + 222), 'Totals by supplier below.', 21, False, INK + (int(255 * e),))
    return lay

def scene_secure(t):
    s = SCENES['secure']['start']; lay = layer(); d = ImageDraw.Draw(lay)
    items = [('Single sign-on', 'One company sign-in'), ('Access per dataset', 'Viewer, Editor or Owner'), ('Activity log', 'Every change is recorded')]
    for i, (title, sub) in enumerate(items):
        a = ease_out(prog(t, s + 0.2 + i * 0.55, 0.6))
        if a <= 0: continue
        x = 120 + i * 360; y = 140 + 24 * (1 - a)
        glass(d, (x, y, x + 330, y + 120))
        d.ellipse((x + 22, y + 36, x + 70, y + 84), fill=(253, 186, 116, int(255 * a))); check(d, x + 46, y + 60, INK + (int(255 * a),), size=10, width=4)
        text(d, (x + 88, y + 46), title, 22, True, (255, 255, 255, int(255 * a)), 'lm')
        text(d, (x + 88, y + 78), sub, 16, False, (220, 228, 255, int(255 * a)), 'lm')
    b = ease_out(prog(t, s + 4.2, 1.0))
    if b > 0:
        card(d, (W / 2 - 300, 320 + 30 * (1 - b), W / 2 + 300, 600), radius=26, fill=(255, 255, 255, int(245 * b)))
        logo(lay, W / 2, 380, int(80 * pop(prog(t, s + 4.2, 1.0)))); d = ImageDraw.Draw(lay)
        text(d, (W / 2, 450), "You're ready.", 30, True, INK + (int(255 * b),), 'mm')
        c = ease_out(prog(t, s + 5.4, 0.7))
        if c > 0:
            card(d, (W / 2 - 150, 492, W / 2 + 150, 548), radius=28, fill=(29, 45, 107, int(255 * c)))
            text(d, (W / 2, 520), 'Start with Quick start', 21, True, (255, 255, 255, int(255 * c)), 'mm')
        text(d, (W / 2, 578), 'Connect · Unify · Ask', 16, True, (90, 100, 130, int(255 * b)), 'mm')
    return lay

RENDER = {'welcome': scene_welcome, 'connect': scene_connect, 'unify': scene_unify, 'ask': scene_ask, 'extract': scene_extract, 'skills': scene_skills, 'secure': scene_secure}

def frame_at(t):
    frame = background(t).convert('RGBA')
    for sid, fn in RENDER.items():
        a = scene_alpha(t, sid)
        if a > 0: frame = composite(frame, fn(t), a)
    # Soft wordmark in the corner the whole way through.
    d = ImageDraw.Draw(frame); text(d, (W - 36, 36), 'lapi', 24, True, (255, 255, 255, 170), 'ra')
    return subtitle(frame, t).convert('RGB')

if __name__ == '__main__':
    only = int(sys.argv[1]) if len(sys.argv) > 1 else None
    if only is not None:  # one preview frame at a time (seconds)
        frame_at(float(sys.argv[1])).save(HERE / f'preview-{sys.argv[1]}.png'); print('preview', sys.argv[1]); sys.exit()
    for i in range(TOTAL_FRAMES):
        frame_at(i / FPS).save(FRAMES / f'f{i:05d}.jpg', quality=93)
        if i % 300 == 0: print('frame', i, '/', TOTAL_FRAMES, flush=True)
    print('done', TOTAL_FRAMES, 'frames', END, 'seconds')
