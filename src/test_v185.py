# -*- coding: utf-8 -*-
"""Smoke test v1.8.5 — ĐỌC BÁO QUỐC TẾ CNN / BBC / FOX NEWS (ngẫu nhiên 1 trang, bấm 1 bài).

Chạy OFFLINE: python src\\test_v185.py
"""
import os
import re
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
os.environ["GPM_BOT_DATA_DIR"] = tempfile.mkdtemp(prefix="gpm_v185_")

from src.workflow.warmup import WarmupWorkflow  # noqa: E402
from src import lang_profiles  # noqa: E402

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


print("\n== 1. 3 trang báo + mẫu link bài (từ DOM thật 19/11/2026)")
sites = {n: (u, d, p) for n, u, d, p in WarmupWorkflow.WORLD_NEWS_SITES}
check("đủ CNN / BBC / Fox News", set(sites) == {"CNN", "BBC", "Fox News"}, str(list(sites)))
CASES = {
    "CNN": (["edition.cnn.com/2026/11/18/politics/nsa-outage-disrupts-georgia-intel-hub-middle-east",
             "edition.cnn.com/2026/07/06/science/golden-man-scythians-heredity-status",
             "www.cnn.com/2026/11/18/tech/anthropic-ipo-cofounders/index.html"],
            ["edition.cnn.com/2026/11/18/us/video/trump-fox-interview-tech-outages-relax-digvid-hnk",
             "edition.cnn.com/travel/hittites-ancient-turkey-empire", "edition.cnn.com/world/africa",
             "www.cnn.com/newsletters/what-matters?source=growth"]),
    "BBC": (["www.bbc.com/news/articles/c6e9kn15z9d7o", "www.bbc.com/sport/cricket/articles/cqwy41w3zydgo",
             "www.bbc.co.uk/news/articles/cq62ped2ypy4o"],
            ["www.bbc.com/news/videos/cmx2ryw97x4go", "www.bbc.com/audio/series/p02nq0gn",
             "www.bbc.com/news/live/c123", "www.bbc.com/sport"]),
    "Fox News": (["www.foxnews.com/world/irish-activist-indicted-us-alleged-destruction-60m-military-plane",
                  "www.foxnews.com/outkick-sports/wnba-launches-search-next-commissioner-outgoing",
                  "www.foxnews.com/politics/jeffries-brushes-off-opposition-far-left-dems"],
                 ["www.foxnews.com/video/6408561515112", "www.foxnews.com/category/us/digital-originals",
                  "www.foxnews.com/live-news/trump-to-meet-xi", "www.foxnews.com/deals/travel-comfort-essentials",
                  "www.foxnews.com/politics/politics-cartoons-slideshow"]),
}
for name, (good, bad) in CASES.items():
    pat = re.compile(sites[name][2], re.I)
    check(f"{name}: nhận đúng link bài", all(pat.search(u) for u in good),
          str([u for u in good if not pat.search(u)]))
    check(f"{name}: loại video/danh mục/podcast", not any(pat.search(u) for u in bad),
          str([u for u in bad if pat.search(u)]))

print("\n== 2. Có trong lịch hành động cả 3 pha")


class Ctx:
    def on(self, *a, **k):
        return None


src = open(os.path.join(SRC, "workflow", "warmup.py"), encoding="utf-8").read()
i_run = src.index("def run_random_session")
body = src[i_run:i_run + 9000]
check("3 pha đều có read_world_news", body.count('"read_world_news": (self.action_read_world_news,') == 3)
wf = WarmupWorkflow(context=Ctx())
check("action_read_world_news tồn tại", callable(getattr(wf, "action_read_world_news", None)))

print("\n== 3. Chọn trang NGẪU NHIÊN + đi qua cổng Google + bấm đúng 1 bài")


class Stop(Exception):
    pass


seen = Counter()
domains = []


def fake_nav(page, kw, domain):
    domains.append((kw, domain))
    raise Stop()


wf._navigate_via_google = fake_nav
wf.DIRECT_VISIT_P = 0.0   # v1.8.6: đo việc CHỌN báo + cổng Google, không đi nhánh gõ thẳng
for _ in range(300):
    wf.action_read_world_news(object())
for kw, d in domains:
    seen[d] += 1
check("cả 3 trang đều được chọn (300 lượt)", set(seen) == {"cnn.com", "bbc.com", "foxnews.com"}, str(dict(seen)))
check("phân bổ đều (mỗi trang ≥ 20%)", min(seen.values()) >= 60, str(dict(seen)))
check("từ khóa Google là cụm tin tức hoặc chủ đề của profile (v1.8.6)",
      all(kw in WarmupWorkflow.WORLD_NEWS_QUERIES or kw == wf.session_theme.get("google_query") for kw, _ in domains))
a = src.index("def action_read_world_news")
act = src[a:src.index("def action_watch_video", a)]
check("đi qua _navigate_via_google, goto thẳng chỉ có nhãn (Fallback Google)",
      "self._navigate_via_google(" in act and "(Fallback Google)" in act)
check("chỉ đánh dấu và bấm 1 bài (data-gpm-pick)", act.count("a[data-gpm-pick='1']") == 1
      and "for attempt" in act and "num_clicks" not in act)
check("bấm bằng Locator.click sau khi rê Bezier (ổn định hơn bấm tọa độ)",
      "self.move_mouse_bezier(page, link)" in act and "link.click(timeout=8000)" in act
      and "self.human_click(page, link)" not in act)
check("đọc bài 2.5-5.5 phút như v1.6.4", "self._simulate_scroll_and_read(active, 150, 330)" in act)

print("\n== 4. Danh sách báo tiếng Anh (đọc báo thường) có Fox News")
check("lang_profiles en có foxnews.com", ("https://www.foxnews.com/", "foxnews.com") in lang_profiles.news_sites("en"))
ui = open(os.path.join(SRC, "ui_main.py"), encoding="utf-8").read()
check("CHI TIẾT chế độ ngâm có dòng CNN/BBC/Fox ở 3 pha", ui.count('("Báo quốc tế CNN/BBC/Fox",') == 3)

print(f"\nPASS: {PASS}   FAIL: {FAIL}")
print("SMOKE v1.8.5: ALL PASS" if FAIL == 0 else "SMOKE v1.8.5: CO LOI")
sys.exit(0 if FAIL == 0 else 1)
