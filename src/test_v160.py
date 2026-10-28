# -*- coding: utf-8 -*-
"""Smoke test v1.6.1 — NÚT CHỌN NGÔN NGỮ TỪ KHÓA (Việt / Anh / Nhật / Hàn).

User yêu cầu: thêm nút chọn ngôn ngữ (1 Việt, 2 Anh, 3 Nhật, 4 Hàn). Ngôn ngữ chọn
chi phối: (a) prompt sinh chủ đề, (b) mẫu offline, (c) prompt plan + keyword runtime,
(d) pool bước offline, (e) báo đọc theo ngôn ngữ, (f) thời tiết, (g) default fallback.

OFFLINE (không cần browser). Chạy:  python src\\test_v160.py
DB/config test nằm ở thư mục tạm (GPM_BOT_DATA_DIR) — KHÔNG đụng data\\ thật.
"""
import os
import random
import sys
import tempfile

SRC = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SRC)
for p in (ROOT, SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TMP = tempfile.mkdtemp(prefix="gpm_v160_")
os.environ["GPM_BOT_DATA_DIR"] = TMP

PASS = 0
FAIL = 0


def check(label, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {label}" + (f"  ({extra})" if extra else ""))
    else:
        FAIL += 1
        print(f"  [FAIL] {label}" + (f"  ({extra})" if extra else ""))


def hr(t):
    print("\n" + "=" * 70)
    print(t)
    print("=" * 70)


def read_src(rel):
    with open(os.path.join(ROOT, rel), "r", encoding="utf-8") as f:
        return f.read()


from src import lang_profiles as L  # noqa: E402
import src.ui_main as ui  # noqa: E402


# =====================================================================
hr("1. lang_profiles — chuẩn hoá + câu ép ngôn ngữ + bộ dữ liệu 4 thứ tiếng")
# =====================================================================
check("LANG_CODES đủ 4", L.LANG_CODES == ("vi", "en", "ja", "ko"))
check("norm rác -> default en", L.norm("xx") == "en" and L.norm("") == "en")
check("norm nhận hoa/thường/space", L.norm(" JA ") == "ja")
check("nhãn UV đủ 4 (Việt/Anh/Nhật/Hàn)",
      [L.LANG_LABELS[c] for c in L.LANG_CODES] == ["Tiếng Việt", "Tiếng Anh", "Tiếng Nhật", "Tiếng Hàn"])
check("clause en nói English", "English" in L.prompt_lang_clause("en"))
check("clause ja nói Japanese", "Japanese" in L.prompt_lang_clause("ja"))
check("clause ko nói Korean", "Korean" in L.prompt_lang_clause("ko"))
check("clause vi nói Vietnamese", "Vietnamese" in L.prompt_lang_clause("vi"))
for c in L.LANG_CODES:
    check(f"topic_templates[{c}] >=10 mẫu + có {{s}}",
          len(L.topic_templates(c)) >= 10 and all("{s}" in t for t in L.topic_templates(c)))
    check(f"news_sites[{c}] >=5 (url,domain)",
          len(L.news_sites(c)) >= 5 and all(len(x) == 2 for x in L.news_sites(c)))
    check(f"weather_queries[{c}] >=3", len(L.weather_queries(c)) >= 3)
    check(f"plan_pool[{c}] có đủ 6 nền tảng",
          set(p for p, _ in L.plan_pool(c)) >= {"google", "youtube", "maps", "news", "wikipedia", "tiktok"})
    check(f"session_default[{c}] đủ 2 key",
          set(L.session_default(c)) == {"google_query", "youtube_query"})
    check(f"default_kw[{c}] 'news' không rỗng", bool(L.default_kw(c, "news")))
# báo phải KHÁC nhau giữa vi và ja (xác nhận thật sự đổi theo ngôn ngữ)
check("news vi != news en", L.news_sites("vi")[0] != L.news_sites("en")[0])
check("news ja != news ko", L.news_sites("ja")[0] != L.news_sites("ko")[0])
check("weather ja là tiếng Nhật", "天気" in L.weather_queries("ja")[0])
check("weather ko là tiếng Hàn", "날씨" in L.weather_queries("ko")[0])


# =====================================================================
hr("2. generate_topics_from_seed — theo lang (offline + prompt AI)")
# =====================================================================
gen = ui.generate_topics_from_seed


class FakeBrain:
    def __init__(self, text):
        self.text = text
        self.last_prompt = ""

    def ask_text(self, prompt):
        self.last_prompt = prompt
        return self.text


# offline: template đúng ngôn ngữ (seed English để thấy rõ phần template)
# rng cố định -> không còn flaky (trước đây shuffle 16 mẫu lấy 4 đầu, đôi khi hụt marker)
tv = gen("walking", 4, brain=None, rng=random.Random(0), lang="vi")
check("offline vi dùng mẫu tiếng Việt", any("cửa hàng" in t["google_query"] or "mua" in t["google_query"] or "cách" in t["google_query"] for t in tv), str([t["google_query"] for t in tv]))
tj = gen("walking", 4, brain=None, lang="ja")
check("offline ja dùng ký tự tiếng Nhật", any(any(ord(ch) > 0x3000 for ch in t["google_query"]) for t in tj), str([t["google_query"] for t in tj]))
tk = gen("walking", 4, brain=None, lang="ko")
check("offline ko dùng ký tự tiếng Hàn", any(any(0xAC00 <= ord(ch) <= 0xD7A3 for ch in t["google_query"]) for t in tk), str([t["google_query"] for t in tk]))
# đủ n + phân biệt mọi ngôn ngữ
for c in L.LANG_CODES:
    r = gen("du lịch", 6, brain=None, lang=c)
    check(f"offline {c}: đúng 6 + phân biệt", len(r) == 6 and len({x["google_query"] for x in r}) == 6)

# prompt AI mang đúng tên ngôn ngữ
fb = FakeBrain("a | b\nc | d\ne | f\n")
gen("cooking", 3, brain=fb, lang="ja")
check("prompt AI (ja) ép Japanese", "Japanese" in fb.last_prompt)
gen("cooking", 3, brain=fb, lang="ko")
check("prompt AI (ko) ép Korean", "Korean" in fb.last_prompt)
gen("cooking", 3, brain=fb, lang="vi")
check("prompt AI (vi) ép Vietnamese", "Vietnamese" in fb.last_prompt)
# lang rác -> rơi về en (an toàn)
gen("cooking", 2, brain=fb, lang="zz")
check("lang rác -> English", "English" in fb.last_prompt)


# =====================================================================
hr("3. WarmupWorkflow(keyword_lang=...) — runtime đổi theo ngôn ngữ")
# =====================================================================
from src.workflow.warmup import WarmupWorkflow  # noqa: E402


class FakeCtx:
    def on(self, *a, **k):
        pass


for c in L.LANG_CODES:
    wf = WarmupWorkflow(FakeCtx(), profile_id="p", keyword_lang=c)
    check(f"wf.keyword_lang == {c}", wf.keyword_lang == c)
    check(f"session_theme default theo {c}", wf.session_theme == L.session_default(c))
    check(f"_dkw('news') theo {c}", wf._dkw("news") == L.default_kw(c, "news"))
    plan = wf._local_plan_steps("walking")
    check(f"_local_plan_steps {c}: 6-10 bước + đủ nền tảng",
          6 <= len(plan) <= 10 and set(s["platform"] for s in plan) >= {"google", "youtube", "maps", "news", "wikipedia", "tiktok"})

# keyword_lang rác -> en
wf2 = WarmupWorkflow(FakeCtx(), profile_id="p", keyword_lang="zz")
check("keyword_lang rác -> en", wf2.keyword_lang == "en")
# prompt plan + keyword mang đúng ngôn ngữ (dùng FakeBrain)
wf3 = WarmupWorkflow(FakeCtx(), profile_id="p", brain=FakeBrain("google | x\nyoutube | y\nmaps | z\nnews | w\n"), keyword_lang="ja")
wf3._safe_ask_plan("walking")
check("prompt plan runtime (ja) ép Japanese", "Japanese" in wf3.brain.last_prompt)
wf3._safe_ask_keyword(topic_hint="walking")
check("prompt keyword runtime (ja) ép Japanese", "Japanese" in wf3.brain.last_prompt)


# =====================================================================
hr("4. Nguồn tĩnh — wiring & news/weather theo ngôn ngữ")
# =====================================================================
wu = read_src("src/workflow/warmup.py")
um = read_src("src/ui_main.py")
cfg = read_src("src/app_config.py")
check("warmup import lang_profiles as _LANG", "import lang_profiles as _LANG" in wu)
check("warmup __init__ nhận keyword_lang", "keyword_lang=\"en\"" in wu and "self.keyword_lang = _LANG.norm(keyword_lang)" in wu)
check("action_read_news dùng _LANG.news_sites", "_LANG.news_sites(self.keyword_lang)" in wu)
check("action_search_weather dùng _LANG.weather_queries", "_LANG.weather_queries(self.keyword_lang)" in wu)
check("_local_plan_steps dùng _LANG.plan_pool", "_LANG.plan_pool(self.keyword_lang)" in wu)
check("prompt plan/keyword dùng _LANG.prompt_lang_clause", wu.count("_LANG.prompt_lang_clause(self.keyword_lang)") >= 2)
check("ui_main import lang_profiles", "from src import lang_profiles" in um)
check("generate_topics_from_seed có param lang", "def generate_topics_from_seed(seed, n, brain=None, rng=None, log=None, lang=\"en\")" in um)
check("WarmupWorkflow nhận keyword_lang=keyword_lang", "keyword_lang=keyword_lang" in um)
check("run_single_profile có keyword_lang trong chữ ký", "assigned_theme=None, keyword_lang=\"en\")" in um)
check("app_config DEFAULTS có keyword_lang", '"keyword_lang": "en"' in cfg)


# =====================================================================
hr("5. GUI — 4 nút radio + _keyword_lang + persist config")
# =====================================================================
import tkinter as tk  # noqa: E402
from tkinter import ttk  # noqa: E402

root = tk.Tk()
app = ui.AutomationApp(root)
root.update()

check("Có var_kw_lang", hasattr(app, "var_kw_lang"))
check("_keyword_lang() trả mã hợp lệ", app._keyword_lang() in L.LANG_CODES)


def _count_lang_radios(widget):
    n = 0
    try:
        for w in widget.winfo_children():
            if isinstance(w, ttk.Radiobutton):
                try:
                    if str(w.cget("value")) in L.LANG_CODES:
                        n += 1
                except Exception:
                    pass
            n += _count_lang_radios(w)
    except Exception:
        pass
    return n


check("Có đúng 4 radio ngôn ngữ", _count_lang_radios(root) == 4, str(_count_lang_radios(root)))

# đổi ngôn ngữ -> _keyword_lang theo + persist config round-trip
app.var_kw_lang.set("ja")
check("set 'ja' -> _keyword_lang()=='ja'", app._keyword_lang() == "ja")
app._on_kw_lang_changed()  # lưu config
from src.app_config import load_config  # noqa: E402
check("config lưu keyword_lang='ja'", load_config().get("keyword_lang") == "ja")
app.var_kw_lang.set("ko")
app.save_current_config()
check("save_current_config lưu 'ko'", load_config().get("keyword_lang") == "ko")

# on_generate_topics đọc đúng ngôn ngữ (offline, ép _detect->None cho tất định)
app.var_brain_type.set("none")
_orig_detect = ui._detect_brain_type_from_env
ui._detect_brain_type_from_env = lambda: None
app.var_kw_lang.set("ja")
app.var_pinned_theme.set("du lịch")
app.profile_rows = [{"id": "00000000-0000-0000-0000-000000000000", "name": "P0",
                     "firefox": False, "hidden": False, "var": tk.BooleanVar(value=True)}]
captured = {}
app._show_generated_topics_preview = lambda seed, topics: captured.update(topics=topics)
app.on_generate_topics()
import time as _t
_dl = _t.time() + 5
while "topics" not in captured and _t.time() < _dl:
    root.update()
    _t.sleep(0.02)
check("on_generate_topics (ja, offline) ra chủ đề tiếng Nhật",
      bool(captured.get("topics")) and any(any(ord(ch) > 0x3000 for ch in t["google_query"]) for t in captured["topics"]),
      str([t["google_query"] for t in captured.get("topics", [])]))
ui._detect_brain_type_from_env = _orig_detect

try:
    root.destroy()
except Exception:
    pass

# =====================================================================
print("\n" + "=" * 70)
print(f"PASS: {PASS}   FAIL: {FAIL}")
print("SMOKE v1.6.1: ALL PASS" if FAIL == 0 else "SMOKE v1.6.1: CÓ LỖI")
print("=" * 70)
sys.exit(1 if FAIL else 0)
