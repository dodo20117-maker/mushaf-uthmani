"""
مصدر النص ورسم الآيات.
النص: بيانات مجمع الملك فهد لطباعة المصحف الشريف (KFGQPC Hafs Uthmanic Data v18)
الخط: خط حفص العثماني الرسمي من المجمع (hafs.18.ttf)
لا يُعدَّل النص بأي شكل؛ يُرسم كما هو حرفًا بحرف.
"""
import hashlib
import io
import json
import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, features

BASE = Path(__file__).parent
DATA_FILE = BASE / "hafsData_v18.json"
FONT_FILE = BASE / "hafs.18.ttf"

# بصمات الملفات الأصلية — إن تغيّر حرف واحد يرفض الخادم العمل
EXPECTED_SHA256 = {
    DATA_FILE: "5d8bb91726e482839d0057633cb1973031e4d706fa9604eea5e08892f20ba140",
    FONT_FILE: "a0636e68e375af9552470d67773936f54d536e6586ce2608311b2fe7f9cbec3a",
}
NBSP = " "


def verify_integrity() -> None:
    for path, expected in EXPECTED_SHA256.items():
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"تم تعديل الملف {path.name}؛ البصمة غير مطابقة للمصدر الرسمي")
    if not features.check("raqm"):
        raise RuntimeError("مكتبة raqm غير متوفرة؛ لا يمكن تشكيل الحروف العربية تشكيلًا صحيحًا")


verify_integrity()
AYAT = json.loads(DATA_FILE.read_text(encoding="utf-8"))
BY_KEY = {(a["sora"], a["aya_no"]): a for a in AYAT}
SURAHS = {}
for a in AYAT:
    s = SURAHS.setdefault(a["sora"], {"number": a["sora"], "name_ar": a["sora_name_ar"],
                                       "name_en": a["sora_name_en"], "ayat": 0})
    s["ayat"] += 1


class QuranError(ValueError):
    pass


def get_range(sura: int, from_aya: int, to_aya: int | None = None) -> list[dict]:
    if sura not in SURAHS:
        raise QuranError("رقم السورة يجب أن يكون بين 1 و114")
    to_aya = to_aya or from_aya
    count = SURAHS[sura]["ayat"]
    if not (1 <= from_aya <= to_aya <= count):
        raise QuranError(f"سورة {SURAHS[sura]['name_ar']} عدد آياتها {count}")
    if to_aya - from_aya >= 40:
        raise QuranError("الحد الأقصى 40 آية في الطلب الواحد")
    return [BY_KEY[(sura, n)] for n in range(from_aya, to_aya + 1)]


def strip_aya_number(text: str) -> str:
    # رقم الآية في البيانات مفصول بمسافة غير منكسرة في آخر النص؛ نحذفه فقط ولا نلمس الآية
    return text.rsplit(NBSP, 1)[0] if NBSP in text else text


def uthmani_text(ayat: list[dict], with_numbers: bool = True) -> str:
    parts = [a["aya_text"] if with_numbers else strip_aya_number(a["aya_text"]) for a in ayat]
    return " ".join(parts)


# ---------- البحث ----------
_DIAC = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")


def normalize(s: str) -> str:
    s = _DIAC.sub("", s)
    s = re.sub("[إأآٱا]", "ا", s)
    s = s.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    return re.sub(r"\s+", " ", s).strip()


_INDEX = [(normalize(a["aya_text_emlaey"]), a) for a in AYAT]


def search(query: str, limit: int = 10) -> list[dict]:
    q = normalize(query)
    if len(q) < 2:
        raise QuranError("اكتب كلمتين أو أكثر من الآية")
    words = q.split()
    hits = [a for norm, a in _INDEX if all(w in norm for w in words)]
    exact = [a for a in hits if q in normalize(a["aya_text_emlaey"])]
    ordered = exact + [a for a in hits if a not in exact]
    return ordered[:limit]


# ---------- الرسم ----------
@lru_cache(maxsize=16)
def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_FILE), size, layout_engine=ImageFont.Layout.RAQM)


def _hex(color: str, alpha: int = 255) -> tuple:
    c = color.lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", c):
        raise QuranError("اللون يجب أن يكون بصيغة hex مثل #000000")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4)) + (alpha,)


def render_png(text: str, *, font_size: int = 96, max_width: int = 2000,
               color: str = "#000000", background: str | None = None,
               align: str = "center", line_spacing: float = 1.9, padding: int | None = None) -> bytes:
    """يرسم النص بخط المجمع. السطور تُكسر عند المسافات بين الكلمات فقط."""
    font_size = max(24, min(int(font_size), 300))
    max_width = max(400, min(int(max_width), 6000))
    pad = int(font_size * 0.6) if padding is None else max(0, int(padding))
    f = _font(font_size)
    measurer = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    def width(t: str) -> int:
        return int(measurer.textlength(t, font=f, direction="rtl", language="ar"))

    inner = max_width - 2 * pad
    lines, cur = [], ""
    for word in text.split(" "):
        trial = f"{cur} {word}" if cur else word
        if cur and width(trial) > inner:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)

    line_h = int(font_size * line_spacing)
    widths = [width(l) for l in lines]
    img_w = (max(widths) if len(lines) == 1 else inner) + 2 * pad
    img_h = line_h * len(lines) + 2 * pad
    bg = _hex(background) if background else (0, 0, 0, 0)
    img = Image.new("RGBA", (img_w, img_h), bg)
    d = ImageDraw.Draw(img)
    fill = _hex(color)
    for i, (line, w) in enumerate(zip(lines, widths)):
        if align == "right":
            x = img_w - pad - w
        elif align == "left":
            x = pad
        else:
            x = (img_w - w) // 2
        y = pad + i * line_h + line_h // 2
        d.text((x, y), line, font=f, fill=fill, direction="rtl", language="ar", anchor="lm")
    bbox = img.getbbox() if not background else None
    if bbox:  # قص الفراغ الزائد مع إبقاء الهامش
        l, t, r, b = bbox
        img = img.crop((max(0, l - pad), max(0, t - pad), min(img_w, r + pad), min(img_h, b + pad)))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def reference(ayat: list[dict]) -> str:
    a, b = ayat[0], ayat[-1]
    name = a["sora_name_ar"]
    return f"[{name}: {a['aya_no']}]" if a is b else f"[{name}: {a['aya_no']}–{b['aya_no']}]"
