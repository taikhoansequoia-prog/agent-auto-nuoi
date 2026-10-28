# -*- coding: utf-8 -*-
"""Smoke test v1.5.2 — 4 yêu cầu của user 20/10/2026, kiểm tra OFFLINE (không cần browser):

  #1 TikTok không bị "vào liên tục" trong 1 phiên: trọng số hạ (clean 0.45->0.15,
     mail 0.20->0.12) + CAP số lượt TikTok theo số hành động của phiên.
  #2 AI Brain chọn 1 CHỦ ĐỀ XUYÊN SUỐT rồi sinh KẾ HOẠCH 8-14 bước nối nhau
     (google -> youtube -> maps -> news -> wikipedia -> tiktok), parse phòng thủ.
  #3 BỎ mô hình "cặp từ khóa" làm trục điều khiển: mọi action lấy từ khóa qua
     _plan_keyword(); cặp cũ chỉ còn là hạt giống / fallback.
  #4 TRẦN THỜI GIAN PHIÊN 15-30 phút (caller ghim "Mục tiêu vòng" thì dùng mốc đó).

Cách chạy:  python src\\test_v152.py
"""
import os
import random
import re
import sys

SRC = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SRC)
for p in (ROOT, SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

from src.workflow.warmup import WarmupWorkflow, _fmt_session_dur  # noqa: E402

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


class FakeContext:
    """Context giả — chỉ cần .on(...) và .new_page() rỗng, không chạy action nào."""

    def on(self, *a, **k):
        return None

    def new_page(self):
        return None


def make_wf(**kw):
    """WarmupWorkflow thật nhưng không cần browser (không chạy action nào)."""
    args = dict(context=FakeContext(), db_handler=None, profile_id=None,
                session_theme={"google_query": "chạy bộ", "youtube_query": "running form"})
    args.update(kw)
    return WarmupWorkflow(**args)


# =====================================================================
# 1. _parse_plan_text — parse kế hoạch AI trả về (cực kỳ phòng thủ)
# =====================================================================
print("\n=== 1. _parse_plan_text ===")
wf = make_wf()

RAW_GOOD = """
google | cách tập chạy bộ đúng cách cho người mới
youtube | hướng dẫn chạy bộ đúng tư thế
google | giày chạy bộ tốt nhất
maps | công viên chạy gần đây
wikipedia | chạy bộ
news | tin tức chạy bộ việt nam
tiktok | chạy bộ buổi sáng
"""
steps = wf._parse_plan_text(RAW_GOOD)
check("7 dòng hợp lệ -> 7 bước", len(steps) == 7, f"n={len(steps)}")
check("platform đúng theo thứ tự",
      [s["platform"] for s in steps] == ["google", "youtube", "google", "maps", "wikipedia", "news", "tiktok"],
      str([s["platform"] for s in steps]))
check("query giữ nguyên chữ", steps[3]["query"] == "công viên chạy gần đây", steps[3]["query"])

# định dạng rác: số thứ tự, dấu đầu dòng, ngoặc, alias tiếng Việt, dòng không có |
RAW_MESSY = """1. google | "cách khởi động trước khi chạy"
- YouTube: không có gạch dọc ở dòng này
* yt | bài tập core cho runner
Bản đồ | quán ăn gần đây
tim kiem | sai lầm khi chạy bộ
wiki | marathon
tt | running tips
google |
maps | từ khóa quá dài """ + ("x" * 120)
steps2 = wf._parse_plan_text(RAW_MESSY)
plats2 = [s["platform"] for s in steps2]
check("bỏ số thứ tự + dấu đầu dòng", plats2[0] == "google", str(plats2))
check("dòng không có '|' bị loại", "youtube" not in plats2 or plats2[0] != "youtube", str(plats2))
check("alias 'yt' -> youtube", "youtube" in plats2, str(plats2))
check("alias 'Bản đồ' -> maps", "maps" in plats2, str(plats2))
check("alias 'tim kiem' -> google", plats2.count("google") >= 2, str(plats2))
check("alias 'wiki'/'tt' -> wikipedia/tiktok",
      "wikipedia" in plats2 and "tiktok" in plats2, str(plats2))
check("query rỗng bị loại", all(s["query"] for s in steps2))
check("query >90 ký tự bị loại", all(len(s["query"]) <= 90 for s in steps2))
check("None/empty -> []", wf._parse_plan_text(None) == [] and wf._parse_plan_text("") == [])

# dedupe + cap 14 (khớp trần 8-14 bước mà prompt yêu cầu AI)
RAW_DUP = "\n".join(["google | trùng nhau"] * 3 + [f"news | chủ đề {i}" for i in range(15)])
steps3 = wf._parse_plan_text(RAW_DUP)
check("dedupe (platform, query)", sum(1 for s in steps3 if s["query"] == "trùng nhau") == 1)
check("cắt tối đa 14 bước", len(steps3) == 14, f"n={len(steps3)}")
_wf_src = open(os.path.join(SRC, "workflow", "warmup.py"), encoding="utf-8").read()
check("trần parse == trần prompt (14)",
      "steps[:14]" in _wf_src and "max_steps=14" in _wf_src,
      "parse cap + prompt cap phải bằng nhau")


# =====================================================================
# 2. _next_plan_step / _plan_keyword — theo chủ đề, không theo cặp
# =====================================================================
print("\n=== 2. _next_plan_step / _plan_keyword ===")
wf = make_wf()
wf.plan_steps = [
    {"platform": "google", "query": "b1 google"},
    {"platform": "youtube", "query": "b2 youtube"},
    {"platform": "google", "query": "b3 google"},
    {"platform": "maps", "query": "b4 maps"},
]
check("bước google đầu tiên", wf._plan_keyword("google", "google_query", "default") == "b1 google")
check("bước google kế tiếp (không lặp)", wf._plan_keyword("google", "google_query", "default") == "b3 google")
check("bước youtube", wf._plan_keyword("youtube", "youtube_query", "default") == "b2 youtube")
check("bước maps", wf._plan_keyword("maps", "google_query", "default") == "b4 maps")
check("hết bước google -> fallback session_theme",
      wf._plan_keyword("google", "google_query", "default") == "chạy bộ")
# LƯU Ý: KHÔNG dùng make_wf(session_theme={}) — dict rỗng là FALSY nên __init__
# (warmup.py L38 `session_theme or {...DEFAULT...}`) sẽ cài theme mặc định,
# làm _plan_keyword trả 'tin tức mới nhất' chứ không phải `default`.
# Muốn test nhánh fallback default thì phải ÉP rỗng SAU khi khởi tạo.
wf_nodefault = make_wf()
wf_nodefault.session_theme = {}
check("không có bước maps còn -> fallback default",
      wf_nodefault._plan_keyword("maps", "google_query", "mặc định") == "mặc định")
wf_empty = make_wf()
check("plan_steps rỗng -> _next_plan_step None", wf_empty._next_plan_step("google") is None)
check("plan rỗng -> _plan_keyword theo theme_key",
      wf_empty._plan_keyword("youtube", "youtube_query") == "running form")


# =====================================================================
# 3. _local_plan_steps — không có AI Brain vẫn có chuỗi chủ đề
# =====================================================================
print("\n=== 3. _local_plan_steps (fallback không AI) ===")
wf = make_wf()
p1 = wf._local_plan_steps("chạy bộ")
p2 = wf._local_plan_steps("chạy bộ")
check("6-10 bước", 6 <= len(p1) <= 10, f"n={len(p1)}")
check("bước đầu luôn google", p1[0]["platform"] == "google", p1[0]["platform"])
check("có maps trong bộ bước", any(s["platform"] == "maps" for s in p1))
check("có youtube trong bộ bước", any(s["platform"] == "youtube" for s in p1))
check("chủ đề seed xuất hiện trong query",
      any("chạy bộ" in s["query"] for s in p1))
_must = ("google", "youtube", "maps", "wikipedia", "news", "tiktok")
_missing = [p for p in _must if not any(s["platform"] == p for s in p1)]
check("ĐỦ 6 nền tảng (không AI vẫn đủ chuỗi)", not _missing, f"thiếu={_missing}")
check("2 lời gọi cho thứ tự khác nhau (RNG)", [s["query"] for s in p1] != [s["query"] for s in p2] or len(p1) <= 2)
check("seed rỗng vẫn chạy", len(make_wf()._local_plan_steps("")) >= 6)


# =====================================================================
# 4. _safe_ask_plan — brain=None -> None; brain lỗi -> None; brain tốt -> steps
# =====================================================================
print("\n=== 4. _safe_ask_plan ===")
wf = make_wf()
check("brain=None -> None (CLI không AI)", wf._safe_ask_plan("chạy bộ") is None)


class FakeBrain:
    def __init__(self, answer, exc=None):
        self.answer = answer
        self.exc = exc
        self.prompts = []

    def ask_text(self, prompt):
        self.prompts.append(prompt)
        if self.exc:
            raise self.exc
        return self.answer


wf = make_wf(brain=FakeBrain(RAW_GOOD))
plan = wf._safe_ask_plan("chạy bộ")
check("brain trả text -> parse được >=4 bước", plan is not None and len(plan) == 7, f"n={len(plan) if plan else 0}")
check("chỉ 1 lượt hỏi AI cho kế hoạch", len(wf.brain.prompts) == 1)
check("prompt nêu đúng seed chủ đề", "chạy bộ" in wf.brain.prompts[0])
check("prompt yêu cầu 8-14 bước", "8-14" in wf.brain.prompts[0])
check("prompt liệt kê đủ nền tảng", all(k in wf.brain.prompts[0] for k in ("google", "youtube", "maps", "news", "wikipedia", "tiktok")))
check("prompt yêu cầu format '<platform> | <keyword'",
      "<platform> | <keyword" in wf.brain.prompts[0],
      "prompt thật: '<platform> | <keyword 3-8 words>'")
# v1.6.0/1.6.1: từ khóa ép ngôn ngữ (mặc định English) + trộn hoạt động thực tế
check("prompt plan ép English (mặc định)", "MUST be in English" in wf.brain.prompts[0])
check("prompt plan nhắc hoạt động thực tế (buy/weather)",
      "buy" in wf.brain.prompts[0].lower() and "weather" in wf.brain.prompts[0].lower())

wf = make_wf(brain=FakeBrain("google | chỉ một dòng"))
check("quá ít bước -> None (dùng dự phòng)", wf._safe_ask_plan("chạy bộ") is None)
wf = make_wf(brain=FakeBrain(None, exc=RuntimeError("API 503")))
check("brain ném exception -> None, không chết phiên", wf._safe_ask_plan("chạy bộ") is None)


# =====================================================================
# 5. _fmt_session_dur
# =====================================================================
print("\n=== 5. _fmt_session_dur ===")
check("0s", _fmt_session_dur(0) == "0s", _fmt_session_dur(0))
check("59s", _fmt_session_dur(59) == "59s", _fmt_session_dur(59))
check("60s -> 1m00s", _fmt_session_dur(60) == "1m00s", _fmt_session_dur(60))
check("900s -> 15m00s", _fmt_session_dur(900) == "15m00s", _fmt_session_dur(900))
check("1800s -> 30m00s", _fmt_session_dur(1800) == "30m00s", _fmt_session_dur(1800))
check("None an toàn", isinstance(_fmt_session_dur(None), str))


# =====================================================================
# 6. TRẦN THỜI GIAN PHIÊN — caller ghim > 0 thắng, 0 -> random 15-30 phút
# =====================================================================
print("\n=== 6. Deadline phiên ===")
wf = make_wf()
check("__init__ mặc định session_deadline_s = 0", getattr(wf, "session_deadline_s", None) == 0)
check("__init__ có plan_steps = []", wf.plan_steps == [])
check("__init__ có _plan_used = set()", isinstance(getattr(wf, "_plan_used", None), set))

code = open(os.path.join(SRC, "workflow", "warmup.py"), encoding="utf-8").read()
rs = code.split("def run_random_session")[1]
dl = rs.split("=== Bản đồ hành động theo GIAI ĐOẠN")[0]
check("nhánh caller dùng session_deadline_s", "self.session_deadline_s and self.session_deadline_s > 0" in dl)
check("nhánh random dùng uniform(15, 30) * 60", "random.uniform(15, 30) * 60" in dl, )
check("lưu mốc ngược lại instance", "self.session_deadline_s = deadline_s" in dl)
check("in log [Giới hạn]", "[Giới hạn]" in dl and "không ngồi cả buổi" in dl)
check("khai báo session_t0", "session_t0 = time.time()" in dl)
check("check mốc ở đầu vòng lặp", "if elapsed >= deadline_s:" in rs)
check("header in đã chạy X/Y", "_fmt_session_dur(elapsed)" in rs and "_fmt_session_dur(deadline_s)" in rs)
check("nghỉ giữa action cũng poll mốc", "time.sleep(0.5)" in rs or "sleep(0.5)" in rs)


# =====================================================================
# 7. TikTok: hạ trọng số + cap lượt/phiên
# =====================================================================
print("\n=== 7. TikTok cap ===")
clean = rs.split('else:\n            # Pha 1 "clean"')[1].split("# Chỉ bổ sung kịch bản YouTube")[0]
mail = rs.split('elif self.phase == "mail":')[1].split('else:\n            # Pha 1 "clean"')[0]
yt = rs.split('if self.phase == "youtube":')[1].split('elif self.phase == "mail":')[0]
check("pha clean TikTok = 0.15", '"action_watch_tiktok": (self.action_watch_tiktok, 0.15)' in clean, )
check("pha mail TikTok = 0.12", '"action_watch_tiktok": (self.action_watch_tiktok, 0.12)' in mail)
check("pha clean KHÔNG còn 0.45", "action_watch_tiktok, 0.45" not in clean)
check("khởi tạo tiktok_runs", "tiktok_runs = 0" in rs)
check("cap = round(total_actions/3), tối thiểu 1",
      "tiktok_cap = max(1, int(round(total_actions / 3))) if total_actions else 1" in rs)
check("pop action_watch_tiktok khi vượt cap",
      'valid_actions.pop("action_watch_tiktok", None)' in rs)
check("có fallback an toàn khi rỗng valid_actions", "if not valid_actions:" in rs)
check("đếm tiktok_runs sau khi chạy", "tiktok_runs += 1" in rs)

# mô phỏng cap: với total_actions=6 -> cap 2
for ta, expect in ((4, 1), (6, 2), (8, 3), (0, 1)):
    cap = max(1, int(round(ta / 3))) if ta else 1
    check(f"total_actions={ta} -> cap {expect}", cap == expect, f"cap={cap}")


# =====================================================================
# 8. Google Maps action — đăng ký đủ 3 pha + platform + selector cấm
# =====================================================================
print("\n=== 8. action_search_maps ===")
check("method tồn tại", hasattr(WarmupWorkflow, "action_search_maps") and callable(WarmupWorkflow.action_search_maps))
check("pha clean có maps 0.30", '"action_search_maps": (self.action_search_maps, 0.30)' in clean)
check("pha mail có maps 0.25", '"action_search_maps": (self.action_search_maps, 0.25)' in mail)
check("pha youtube có maps 0.20", '"action_search_maps": (self.action_search_maps, 0.20)' in yt)
check("_ACTION_PLATFORM có GoogleMaps",
      '"action_search_maps": "GoogleMaps"' in code)

maps_block = code.split("def action_search_maps")[1].split("def action_manage_google_alerts")[0]
check("đi qua cổng Google trước", "_navigate_via_google(" in maps_block)
check("gateway dùng token 'maps'", '"maps")' in maps_block)
check("có nhãn (Fallback Google)", "(Fallback Google)" in maps_block)
check("dùng input[name='q'] của Maps", "input[name='q']" in maps_block)
check("dùng div[role='feed'] / div.Nv2PK", "div[role='feed']" in maps_block and "div.Nv2PK" in maps_block)
check("đọc title bằng h1.DUwDvf", "h1.DUwDvf" in maps_block)
check("tab đánh giá dùng aria-label", "aria-label*='đánh giá'" in maps_block.lower() or "đánh giá" in maps_block)
check("lưu (Lưu) có Escape", "Escape" in maps_block)
check("zoom bằng aria-label Phóng/Thu nhỏ", "Phóng" in maps_block and "Thu nhỏ" in maps_block)
check("kéo bản đồ bằng mouse.wheel", "mouse.wheel" in maps_block)
check("quay lại danh sách bằng go_back", "page.go_back(" in maps_block)
check("toàn bộ bọc try/except", "except Exception" in maps_block)
check("lấy từ khóa theo platform maps từ kế hoạch",
      'self._plan_keyword("maps"' in maps_block)
check("hover/click qua _safe_bbox hoặc is_visible", "_safe_bbox(" in maps_block)
check("cuộn bằng _human_scroll (kiểu người)", "_human_scroll(" in maps_block)

FORBIDDEN = ["ul.rilist", ".place-card", "div.RcArXe", "span.F7nice", "div.iOzk7",
             "Chỉ đường", "Directions", "div.wfPUJd", "div.Jg8qh", "div.RbgeRe",
             "div.FkA0Cd", "abOmTd", "c-wiz", "div.ReBWQe", "div.H9Ol3w", "div.Pea9hb",
             "div.G0rgSb", "span.fewsbb", "review-card", "#searchboxinput", "div.rogA2c",
             "div.IBz9k", "div.HlvSq", "div.PlaLje", "#L2AGLb"]
# Quét trên CODE thật, KHÔNG quét docstring/comment. Bằng chứng cần thiết:
# '#searchboxinput' chỉ xuất hiện trong docstring của action_search_maps dưới dạng
# văn xuôi "(KHÔNG có #searchboxinput)" — nó đang MÔ TẢ selector bị loại, không phải
# selector đang dùng. Quét thô cả khối sẽ báo động giả.
maps_code = re.sub(r'""".*?"""', "", maps_block, flags=re.S)
maps_code = "\n".join(ln for ln in maps_code.splitlines() if not ln.strip().startswith("#"))
hit = [s for s in FORBIDDEN if s in maps_code]
check("KHÔNG dùng selector đã chứng minh là fail", not hit, str(hit))
check("KHÔNG đọc text từng review card (chỉ ngắm)", "review-card" not in maps_code)


# =====================================================================
# 9. Bỏ mô hình cặp: mọi action đọc từ khóa qua _plan_keyword
# =====================================================================
print("\n=== 9. Cặp từ khóa không còn là trục điều khiển ===")
n_plan_kw = len(re.findall(r"self\._plan_keyword\(", code))
check("có >=7 call site _plan_keyword", n_plan_kw >= 7, f"n={n_plan_kw}")
for plat in ("google", "youtube", "maps", "news", "wikipedia", "tiktok"):
    check(f"_plan_keyword('{plat}') được dùng", f'"{plat}"' in code and f"_plan_keyword(\"{plat}\"" in code)
check("không còn đọc session_theme['google_query'] trực tiếp trong action",
      code.count("self.session_theme[\"google_query\"]") <= 3,
      str(code.count("self.session_theme[\"google_query\"]")))
check("plan block trong run_random_session", "self.plan_steps = plan" in rs)
check("fallback 2-lượt-hỏi-cũ khi plan lỗi", "elif self.brain:" in rs)
check("nhánh không AI dùng _local_plan_steps", "self._local_plan_steps(" in rs)
check("log 'không chạy theo cặp'", "không chạy theo cặp" in rs)


# =====================================================================
# 10. UI: session_deadline_s wiring + PHASE_DETAILS + nhãn thẻ chủ đề
# =====================================================================
print("\n=== 10. ui_main.py ===")
ui = open(os.path.join(SRC, "ui_main.py"), encoding="utf-8").read()
check("warmup.session_deadline_s được gán", "warmup.session_deadline_s = int(fixed_target_s)" in ui)
check("0 -> để warmup tự random", "else 0" in ui)
check("in log trần phiên", "Trần phiên" in ui)
check("PHASE_DETAILS có Maps cả 3 pha",
      ui.count('"Google Maps"') >= 3, str(ui.count('"Google Maps"')))
check("PHASE_DETAILS TikTok 0.15 (pha 1)", '("Xem TikTok", 0.15' in ui)
check("PHASE_DETAILS TikTok 0.12 (pha 2)", '("Xem TikTok", 0.12' in ui)
check("PHASE_DETAILS không còn TikTok 0.45", '("Xem TikTok", 0.45' not in ui)
check("notes nói trần 15-30 phút", ui.count("15-30 phút") >= 2, str(ui.count("15-30 phút")))
check("notes nói kế hoạch 8-14 bước", ui.count("8-14 bước") >= 2, str(ui.count("8-14 bước")))
check("card từ khóa đổi nhãn CHỦ ĐỀ XUYÊN SUỐT", "CHỦ ĐỀ XUYÊN SUỐT" in ui)
check("v1.6.6: ô Text nhiều dòng (self.kw_text) thay danh sách row", "self.kw_text" in ui)
check("giữ _collect_kw_pairs (config không vỡ)",
      "_collect_kw_pairs" in ui)
check("giữ total_actions randint(4, 8) (test_v141 coupling)",
      "total_actions = random.randint(4, 8)" in ui)


# =====================================================================
print("\n" + "=" * 68)
print(f"KET QUA: PASS: {PASS}   FAIL: {FAIL}")
print("=" * 68)
print("SMOKE v1.5.2: " + ("ALL PASS" if FAIL == 0 else f"{FAIL} FAIL — CẦN FIX"))
sys.exit(0 if FAIL == 0 else 1)
