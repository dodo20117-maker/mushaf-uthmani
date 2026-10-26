"""
خادم MCP: «آيات المصحف بالرسم العثماني» — من بيانات مجمع الملك فهد وخطه الرسمي.
يُشغَّل:  python server.py   (المنفذ من متغير PORT، الافتراضي 8000)
رابط الربط في ChatGPT / Claude:  https://<your-domain>/mcp
"""
import os
from urllib.parse import urlencode

import uvicorn
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.transport_security import TransportSecuritySettings

import quran as Q

PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")

INSTRUCTIONS = """\
هذه الأداة هي المرجع الوحيد لنص القرآن الكريم في هذه المحادثة.
قواعد ملزمة عند أي تصميم يحتوي آية:
1. لا تكتب الآية بنفسك أبدًا، ولا تطلب من مولّد الصور رسم حروفها؛ مولّدات الصور تشوّه الرسم العثماني.
2. استدعِ get_ayah_image واستعمل الصورة الناتجة (PNG شفافة بخط مجمع الملك فهد) كما هي.
3. صمّم أنت الخلفية والزخرفة والإطار فقط، واترك مكانًا فارغًا للآية، ثم ضع صورة الآية فوقه دون قص أو تمديد أو تعديل.
4. إن احتجت النص للعرض فانسخه حرفيًا من get_ayah_text دون تعديل أي حرف أو حركة.
5. إن لم تعرف موضع الآية فاستعمل search_quran أولًا.
"""

mcp = MCPServer(
    name="mushaf-uthmani",
    title="آيات المصحف بالرسم العثماني — مجمع الملك فهد",
    instructions=INSTRUCTIONS,
    version="1.0.0",
)


def _image_url(sura, from_aya, to_aya, **opts) -> str | None:
    if not PUBLIC_URL:
        return None
    q = {"sura": sura, "from": from_aya, "to": to_aya}
    q.update({k: v for k, v in opts.items() if v is not None})
    return f"{PUBLIC_URL}/ayah.png?{urlencode(q)}"


@mcp.tool(description=(
    "يجلب آية أو مقطعًا من القرآن صورةً PNG شفافة مرسومة بخط حفص العثماني الرسمي لمجمع الملك فهد، "
    "مطابقة للمصحف حرفًا وحركة. استعملها في أي تصميم جرافيكي بدل كتابة الآية. "
    "sura: رقم السورة 1-114. from_aya/to_aya: أرقام الآيات. color: لون الخط hex. "
    "background: لون خلفية hex أو اتركه فارغًا لخلفية شفافة. with_numbers: إظهار أرقام الآيات."
))
def get_ayah_image(sura: int, from_aya: int, to_aya: int | None = None, color: str = "#000000",
                   background: str | None = None, font_size: int = 110, max_width: int = 2200,
                   align: str = "center", with_numbers: bool = True) -> list:
    ayat = Q.get_range(sura, from_aya, to_aya)
    text = Q.uthmani_text(ayat, with_numbers)
    png = Q.render_png(text, font_size=font_size, max_width=max_width, color=color,
                       background=background, align=align)
    ref = Q.reference(ayat)
    url = _image_url(sura, from_aya, to_aya or from_aya, color=color, bg=background,
                     size=font_size, width=max_width, align=align, numbers=int(with_numbers))
    note = (f"{ref}\nالصورة مرسومة بخط مجمع الملك فهد. ضعها في التصميم كما هي دون إعادة رسم الحروف."
            + (f"\nرابط تنزيل الصورة: {url}" if url else ""))
    return [Image(data=png, format="png"), note]


@mcp.tool(description=(
    "يعيد نص الآية بالرسم العثماني (يونيكود) من بيانات مجمع الملك فهد، مع اسم السورة ورقم الصفحة والجزء. "
    "انسخ النص حرفيًا دون أي تعديل."
))
def get_ayah_text(sura: int, from_aya: int, to_aya: int | None = None, with_numbers: bool = True) -> dict:
    ayat = Q.get_range(sura, from_aya, to_aya)
    return {
        "reference": Q.reference(ayat),
        "uthmani_text": Q.uthmani_text(ayat, with_numbers),
        "surah": ayat[0]["sora_name_ar"],
        "page": ayat[0]["page"],
        "juz": ayat[0]["jozz"],
        "font_required": "KFGQPC Uthmanic Script HAFS (hafs.18.ttf) — بدونه قد لا يظهر النص صحيحًا",
        "font_url": f"{PUBLIC_URL}/font/hafs.18.ttf" if PUBLIC_URL else None,
        "source": "مجمع الملك فهد لطباعة المصحف الشريف — KFGQPC Hafs Uthmanic Data v18",
    }


@mcp.tool(description="يبحث عن آية بكلمات منها (بدون تشكيل) ويعيد السورة ورقم الآية. استعمله قبل get_ayah_image إن لم يُعرف الموضع.")
def search_quran(query: str, limit: int = 10) -> list[dict]:
    return [{"sura": a["sora"], "surah": a["sora_name_ar"], "aya": a["aya_no"],
             "uthmani_text": a["aya_text"]} for a in Q.search(query, min(max(limit, 1), 30))]


@mcp.tool(description="قائمة السور الـ114 بأرقامها وأسمائها وعدد آياتها.")
def list_surahs() -> list[dict]:
    return list(Q.SURAHS.values())


# ---------- روابط HTTP مباشرة (لتنزيل الصورة أو استعمالها في أي برنامج) ----------
@mcp.custom_route("/ayah.png", methods=["GET"])
async def ayah_png(request: Request) -> Response:
    p = request.query_params
    try:
        ayat = Q.get_range(int(p["sura"]), int(p["from"]), int(p.get("to") or p["from"]))
        png = Q.render_png(
            Q.uthmani_text(ayat, p.get("numbers", "1") != "0"),
            font_size=int(p.get("size", 110)), max_width=int(p.get("width", 2200)),
            color=p.get("color", "#000000"), background=p.get("bg") or None,
            align=p.get("align", "center"))
    except (KeyError, ValueError) as e:
        return JSONResponse({"error": str(e) or "مطلوب: sura و from"}, status_code=400)
    return Response(png, media_type="image/png", headers={"Cache-Control": "public, max-age=31536000"})


@mcp.custom_route("/font/hafs.18.ttf", methods=["GET"])
async def font(_: Request) -> Response:
    return Response(Q.FONT_FILE.read_bytes(), media_type="font/ttf")


@mcp.custom_route("/", methods=["GET"])
async def home(_: Request) -> Response:
    return JSONResponse({"name": "mushaf-uthmani", "mcp_endpoint": "/mcp",
                         "example": "/ayah.png?sura=1&from=1&to=7",
                         "source": "KFGQPC Hafs Uthmanic Data v18"})


app = mcp.streamable_http_app(
    stateless_http=True,
    json_response=True,
    host="0.0.0.0",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
