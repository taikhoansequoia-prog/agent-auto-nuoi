# -*- coding: utf-8 -*-
"""Smoke test v1.8.6 — GIẢM DẤU HIỆU BOT khi vào báo/TikTok + cảnh báo proxy > 5 acc.

1) ~30% lượt vào báo / báo quốc tế / TikTok GÕ THẲNG địa chỉ (lượt đang theo bước kế hoạch thì vẫn qua Google)
2) Từ khóa tìm báo quốc tế đa dạng (14 cụm + chủ đề của profile khi tiếng Anh)
3) Tiêu đề bị lớp phủ che -> bấm × hoặc cuộn tránh; KHÔNG bấm xuyên (force); chờ Fox chuyển trang tới 25s
4) Tóm tắt proxy nhắc proxy nào đang gánh > 5 acc

Chạy OFFLINE: python src\\test_v186.py
"""
import os
import random
import sys
import tempfile
from collections import Counter

SRC = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SRC)
for p in (ROOT, SRC):
    if p not in sys.path:
        sys.path.insert(0, p)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ["GPM_BOT_DATA_DIR"] = tempfile.mkdtemp(prefix="gpm_v186_")
os.environ["GPM_BOT_ENV_FILE"] = os.path.join(os.environ["GPM_BOT_DATA_DIR"], ".env")

from src.workflow.warmup import WarmupWorkflow  # noqa: E402
import src.ui_main as ui  # noqa: E402

sys.stdout = sys.__stdout__
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


class Ctx:
    def on(self, *a, **k):
        return None


class Stop(Exception):
    pass


def make(lang="en"):
    wf = WarmupWorkflow(context=Ctx(), keyword_lang=lang)
    wf.rng = random.Random(7)
    return wf


print("\n== 1. Tỷ lệ gõ thẳng ~30%, KHÔNG khi đang theo bước kế hoạch")
wf = make()
n = sum(wf._want_direct_visit() for _ in range(4000))
check("~30% lượt gõ thẳng", 0.26 <= n / 4000 <= 0.34, f"{n / 40:.1f}%")
wf._pending_step_idx = 3
check("đang theo bước kế hoạch -> luôn qua Google", not any(wf._want_direct_visit() for _ in range(500)))

print("\n== 2. Đọc báo / TikTok / báo quốc tế: gõ thẳng thì KHÔNG đốt từ khóa kế hoạch, KHÔNG gọi Google")


def run_entry(action, direct_ok=True):
    wf = make()
    wf.DIRECT_VISIT_P = 1.0
    rec = {"direct": [], "google": [], "plan": 0}
    wf._direct_visit = lambda page, url, label: rec["direct"].append(url) or direct_ok
    wf._navigate_via_google = lambda page, kw, dom: rec["google"].append((kw, dom)) or True
    real_plan = wf._plan_keyword

    def plan(*a, **k):
        rec["plan"] += 1
        return real_plan(*a, **k)
    wf._plan_keyword = plan

    def boom(*a, **k):
        raise Stop()
    wf.restore_mouse_position = boom
    wf.random_sleep = boom
    try:
        getattr(wf, action)(object())
    except Stop:
        pass
    return rec


for action, host in (("action_read_news", None), ("action_read_world_news", None), ("action_watch_tiktok", "tiktok.com")):
    r = run_entry(action)
    check(f"{action}: gõ thẳng -> không qua Google, không lấy từ khóa kế hoạch",
          len(r["direct"]) == 1 and not r["google"] and r["plan"] == 0, str(r))
    if host:
        check(f"{action}: mở đúng {host}", host in r["direct"][0], r["direct"][0])
    r2 = run_entry(action, direct_ok=False)
    check(f"{action}: gõ thẳng lỗi -> quay về cổng Google", len(r2["google"]) == 1, str(r2))

print("\n== 3. Từ khóa báo quốc tế đa dạng")
check("≥ 12 cụm tin tức", len(WarmupWorkflow.WORLD_NEWS_QUERIES) >= 12, str(len(WarmupWorkflow.WORLD_NEWS_QUERIES)))
wf = make("en")
wf.session_theme = {"google_query": "home workout for beginners", "youtube_query": "x"}
wf.related_keywords = ["best yoga mat", "resistance bands review"]
qs = Counter(wf._world_news_query() for _ in range(3000))
topic = sum(v for k, v in qs.items() if k in ("home workout for beginners", "best yoga mat", "resistance bands review"))
check("tiếng Anh: ~35% dùng chủ đề của profile", 0.30 <= topic / 3000 <= 0.40, f"{topic / 30:.1f}%")
check("phần còn lại trải đều nhiều cụm", len([k for k in qs if k in WarmupWorkflow.WORLD_NEWS_QUERIES]) >= 12)
wf_vi = make("vi")
wf_vi.session_theme = {"google_query": "chạy bộ buổi sáng", "youtube_query": "x"}
check("tiếng Việt: không ghép chủ đề Việt vào báo Mỹ",
      all(wf_vi._world_news_query() in WarmupWorkflow.WORLD_NEWS_QUERIES for _ in range(300)))

print("\n== 4. Tiêu đề bị che: bấm × / cuộn tránh, không bấm xuyên")


class CoverPage:
    def __init__(self, states):
        self.states = list(states)
        self.locs = []

    def evaluate(self, js, *a):
        return self.states.pop(0) if self.states else {"state": "clear"}

    def locator(self, sel):
        self.locs.append(sel)
        return type("L", (), {"first": sel})()


wf = make()
clicks, scrolls = [], []
wf.human_click = lambda page, el: clicks.append(el)
wf.smooth_scroll = lambda page, d: scrolls.append(d)
wf.random_sleep = lambda *a: None
pg = CoverPage([{"state": "covered", "by": "breaking-news", "close": True}, {"state": "clear"}])
wf._clear_cover(pg, None, "Fox News")
check("có nút × -> bấm đúng nút đánh dấu data-gpm-close", clicks == ["[data-gpm-close='1']"], str(clicks))
clicks.clear()
pg = CoverPage([{"state": "covered", "by": "ad", "close": False}, {"state": "clear"}])


class L:
    def scroll_into_view_if_needed(self, timeout=0):
        pass


wf._clear_cover(pg, L(), "Fox News")
check("không có nút × -> cuộn tránh, không bấm bừa", not clicks and len(scrolls) == 1, f"{clicks} {scrolls}")
scrolls.clear()
wf._clear_cover(CoverPage([{"state": "clear"}]), None, "CNN")
check("không bị che -> không làm gì", not clicks and not scrolls)
src = open(os.path.join(SRC, "workflow", "warmup.py"), encoding="utf-8").read()
a = src.index("def action_read_world_news")
act = src[a:src.index("def action_watch_video", a)]
check("không còn bấm xuyên lớp phủ (force=True)", "force=True" not in act)
check("kiểm tra lớp phủ trước khi bấm", act.index("self._clear_cover(page, link, name)") < act.index("link.click(timeout=8000)"))
check("có hàm chờ bài mở (v1.8.8: bơm sự kiện, không còn con số 25s sai)", "def _wait_article_open(self, page, before, tabs_before, timeout=12, domain=\"\"):" in src)


class P:
    def __init__(self, url):
        self.url = url

    def wait_for_load_state(self, *a, **k):
        pass


wf = make()
main = P("https://www.foxnews.com/tech/a")
newtab = P("https://www.foxnews.com/politics/b")
wf.context = type("C", (), {"pages": [main, newtab]})()
check("bài mở sang TAB MỚI (Fox mở bằng JS, không có target=_blank) -> đọc ở tab mới",
      wf._wait_article_open(main, main.url, [main], 2) is newtab)
wf.context = type("C", (), {"pages": [main]})()
main.url = "https://www.foxnews.com/world/c"
check("cùng tab -> URL đổi là nhận", wf._wait_article_open(main, "https://www.foxnews.com/tech/a", [main], 2) is main)
check("không có gì đổi -> None (mới bấm lại)", wf._wait_article_open(main, main.url, [main], 1) is None)
check("bỏ chữ nguồn ảnh khỏi ứng viên tiêu đề", "getty|images" in src)

print("\n== 5. Cảnh báo proxy gánh > 5 acc")
PM = {f"A{i}": "1.1.1.1:8000:u:p" for i in range(7)}
PM.update({f"B{i}": "2.2.2.2:8000:u:p" for i in range(5)})
PM.update({"C0": "3.3.3.3:9000"})
check("ngưỡng = 5", ui.MAX_ACC_PER_PROXY == 5)
lines = ui.proxy_summary_lines(["A0", "B0", "C0"], PM, 3)
warn = [l for l in lines if l.startswith("[!]")]
check("proxy 7 acc -> nhắc, đếm TỔNG acc trong GPM (không chỉ lô chạy)",
      len(warn) == 1 and "1.1.1.1 = 7 acc" in warn[0], str(warn))
check("proxy đúng 5 acc -> không nhắc", "2.2.2.2" not in " ".join(warn))
check("lô không đụng proxy quá tải -> không nhắc",
      not any(l.startswith("[!]") for l in ui.proxy_summary_lines(["B0", "C0"], PM, 2)))
check("dòng đầu giữ nguyên định dạng v1.8.2", lines[0].startswith("Chặn trùng proxy: BẬT — 3 profile / 3 proxy"), lines[0])

print(f"\nPASS: {PASS}   FAIL: {FAIL}")
print("SMOKE v1.8.6: ALL PASS" if FAIL == 0 else "SMOKE v1.8.6: CO LOI")
sys.exit(0 if FAIL == 0 else 1)
