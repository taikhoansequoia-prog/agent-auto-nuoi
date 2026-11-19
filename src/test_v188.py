# -*- coding: utf-8 -*-
"""Smoke test v1.8.8 — SỬA LỖI SAU KHI RÀ SOÁT v1.8.5-v1.8.7.

1) Vòng chờ "URL đổi / tab mới" phải BƠM sự kiện Playwright (page.wait_for_timeout), không time.sleep
   (bản sync: trong lúc time.sleep, page.url và context.pages đứng yên -> bot tưởng bấm trượt).
2) Tab mới không thuộc trang báo (quảng cáo bật lên) -> đóng, không "đọc" quảng cáo.
3) Kết thúc lượt đọc báo quốc tế: đóng mọi tab phát sinh.
4) Nút × chỉ tìm trong lớp phủ fixed/sticky, trong màn hình.
5) Pha YouTube theo được bước google/news của kế hoạch.

Chạy OFFLINE: python src/test_v188.py
"""
import os
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
os.environ["GPM_BOT_DATA_DIR"] = tempfile.mkdtemp(prefix="gpm_v188_")

from src.workflow.warmup import WarmupWorkflow  # noqa: E402

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
    def __init__(self):
        self.pages = []

    def on(self, *a, **k):
        return None


class LivePage:
    """Giả lập Playwright sync: url/tab CHỈ đổi khi có lệnh Playwright chạy (wait_for_timeout)."""

    def __init__(self, url, ctx=None, on_pump=None):
        self._url = url
        self.ctx = ctx
        self.on_pump = on_pump
        self.pumps = 0
        self.closed = False

    @property
    def url(self):
        return self._url

    def wait_for_timeout(self, ms):
        self.pumps += 1
        if self.on_pump:
            self.on_pump(self)

    def wait_for_load_state(self, *a, **k):
        pass

    def close(self):
        self.closed = True
        if self.ctx and self in self.ctx.pages:
            self.ctx.pages.remove(self)


print("\n== 1. Chờ bài mở: phải bơm sự kiện mới thấy URL đổi")
ctx = Ctx()
wf = WarmupWorkflow(context=ctx)


def nav_after_2(pg):
    if pg.pumps >= 2:
        pg._url = "https://www.foxnews.com/world/some-long-article-slug-here"


main = LivePage("https://www.foxnews.com/", ctx, nav_after_2)
ctx.pages = [main]
got = wf._wait_article_open(main, "https://www.foxnews.com/", [main], 5, domain="foxnews.com")
check("cùng tab: thấy URL đổi nhờ wait_for_timeout", got is main and main.pumps >= 2, f"pumps={main.pumps}")

print("\n== 2. Tab mới: nhận bài báo, đóng tab quảng cáo")
ctx = Ctx()
wf = WarmupWorkflow(context=ctx)
art = LivePage("https://www.foxnews.com/opinion/david-marcus-big-techs-weekend", ctx)
ad = LivePage("https://ads.example-popup.com/win", ctx)


def open_tabs(pg):
    if pg.pumps == 1:
        ctx.pages.append(ad)
    if pg.pumps == 3:
        ctx.pages.append(art)


main = LivePage("https://www.foxnews.com/tech/a", ctx, open_tabs)
ctx.pages = [main]
got = wf._wait_article_open(main, main.url, [main], 6, domain="foxnews.com")
check("tab bài báo (target=_blank) được nhận", got is art)
check("tab quảng cáo bị đóng, không đọc nhầm", ad.closed and ad not in ctx.pages)
main2 = LivePage("https://www.foxnews.com/tech/a", ctx)
ctx.pages = [main2]
check("không có gì xảy ra -> None", wf._wait_article_open(main2, main2.url, [main2], 1, domain="foxnews.com") is None)

print("\n== 3. _pump_wait: có wait_for_timeout thì dùng, không có thì vẫn chờ được")
pg = LivePage("x")
wf._pump_wait(pg, 0.01)
check("gọi page.wait_for_timeout", pg.pumps == 1)
wf._pump_wait(object(), 0.01)
check("page giả không có wait_for_timeout -> không lỗi", True)

print("\n== 4. Kiểm tra tĩnh trên mã nguồn")
src = open(os.path.join(SRC, "workflow", "warmup.py"), encoding="utf-8").read()
g = src.index("def _navigate_via_google")
gate = src[g:src.index("def _preview_sweep_browse", g)]
check("cổng Google: vòng chờ URL dùng _pump_wait", "self._pump_wait(page, random.uniform(0.4, 0.9))" in gate
      and "self.random_sleep(0.4, 0.9)" not in gate)
a = src.index("def action_read_world_news")
act = src[a:src.index("def action_watch_video", a)]
check("đóng mọi tab phát sinh khi xong", "if _p is not page and _p not in tabs_before:" in act and "_p.close()" in act)
check("chờ bài mở có truyền domain", act.count("domain=domain)") == 2)
c = src.index("_COVER_CHECK_JS = r")
cover = src[c:src.index("def _clear_cover", c)]
check("nút × chỉ tìm trong lớp phủ fixed/sticky", "pos === 'fixed' || pos === 'sticky'" in cover and "layer.querySelectorAll" in cover)
check("nút × phải nằm trong màn hình", "q.bottom > innerHeight" in cover)
check("JS cân ngoặc", cover.count("{") == cover.count("}") and cover.count("(") == cover.count(")"),
      f"{cover.count('{')}/{cover.count('}')}")

print("\n== 5. Pha YouTube theo được bước google/news của kế hoạch")
wf = WarmupWorkflow(context=Ctx(), phase="youtube")
wf.plan_steps = [{"platform": "news", "query": "running shoes news"}, {"platform": "google", "query": "best running shoes"}]
wf._plan_used = set()
yt_actions = {"watch_video": 1, "action_search_youtube": 1, "action_read_news": 1, "action_read_wikipedia": 1}
check("bước news -> action_read_news (trước đây None)", wf._pick_plan_action(yt_actions) == ("action_read_news", 0),
      str(wf._pick_plan_action(yt_actions)))
wf._plan_used = {0}
check("bước google -> action_read_news ở pha YouTube", wf._pick_plan_action(yt_actions) == ("action_read_news", 1))
clean = {"read_news": 1, "search_google": 1}
wf._plan_used = set()
check("pha 1/2 không đổi: news -> read_news", wf._pick_plan_action(clean) == ("read_news", 0))
wf._plan_used = {0}
check("pha 1/2 không đổi: google -> search_google", wf._pick_plan_action(clean) == ("search_google", 1))

print("\n== 6. Trang đáp không có bài (vd cnn-underscored) -> về trang chủ báo")
check("so đúng địa chỉ trang chủ, không so 'chứa chuỗi'",
      '.rstrip("/") != home_url.rstrip("/"):' in act and 'home_url.rstrip("/") not in page.url' not in act)


class NoArticlePage:
    def __init__(self):
        self.url = "https://edition.cnn.com/cnn-underscored/electronics"
        self.gotos = []

    def goto(self, url, **k):
        self.gotos.append(url)
        self.url = url


class Halt(Exception):
    pass


wf = WarmupWorkflow(context=Ctx())
wf.WORLD_NEWS_SITES = tuple(x for x in WarmupWorkflow.WORLD_NEWS_SITES if x[0] == "CNN")
wf.DIRECT_VISIT_P = 0.0
wf._navigate_via_google = lambda page, kw, dom: True
wf.restore_mouse_position = lambda page: None
wf.random_sleep = lambda *a: None
wf._close_popups = lambda page: None
wf._simulate_scroll_and_read = lambda *a, **k: None
wf._human_scroll = lambda *a, **k: None
picks = []


def pick(page, pat, host):
    picks.append(page.url)
    return None


wf._pick_world_article = pick
npg = NoArticlePage()
wf.action_read_world_news(npg)
check("đang ở trang con cùng tên miền -> quay về trang chủ CNN rồi chọn bài lại",
      npg.gotos == ["https://edition.cnn.com/"] and picks[-1].rstrip("/") == "https://edition.cnn.com",
      f"{npg.gotos} {picks[-1:]}")
home = NoArticlePage()
home.url = "https://edition.cnn.com/"
wf.action_read_world_news(home)
check("đã ở đúng trang chủ mà không có bài -> không goto lặp lại", home.gotos == [], str(home.gotos))

print(f"\nPASS: {PASS}   FAIL: {FAIL}")
print("SMOKE v1.8.8: ALL PASS" if FAIL == 0 else "SMOKE v1.8.8: CO LOI")
sys.exit(0 if FAIL == 0 else 1)
