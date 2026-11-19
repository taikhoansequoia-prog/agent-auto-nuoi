# -*- coding: utf-8 -*-
"""Smoke test v1.9.0 — 2 điểm lộ ra ở LÔ THẬT CUỐI (5 profile, 19/11/2026).

1) Tab Tin tức của Google mở ra KHÔNG có bài nào (warmup 17 đọc 0/2 bài) -> quay lại tab Tất cả, đọc kết quả thường
2) Back quá hạn và chưa về Google -> không tải lại trang báo thừa 1 lượt, mở thẳng lại trang kết quả

Chạy OFFLINE: python src/test_v190.py
"""
import io
import os
import random
import sys
import tempfile
from contextlib import redirect_stdout

SRC = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SRC)
for p in (ROOT, SRC):
    if p not in sys.path:
        sys.path.insert(0, p)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ["GPM_BOT_DATA_DIR"] = tempfile.mkdtemp(prefix="gpm_v190_")
os.environ["GPM_BOT_ENV_FILE"] = os.path.join(os.environ["GPM_BOT_DATA_DIR"], ".env")

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


NEWS_SEL = "a[jsname='YKoRaf'], a.WlydOe"
ORG_SEL = "#rso a:has(h3), #search a:has(h3)"
SERP_ALL = "https://www.google.com/search?q=home+gym"
SERP_NEWS = "https://www.google.com/search?q=home+gym&tbm=nws"


class Link:
    def __init__(self, page, href, kind, vis=True):
        self.page, self.href, self.kind, self.vis = page, href, kind, vis

    def is_visible(self, timeout=None):
        return self.vis

    def get_attribute(self, name):
        return self.href

    @property
    def first(self):
        return self


class Group:
    def __init__(self, items, visible=True):
        self.items, self._vis = items, visible

    def all(self):
        return list(self.items)

    @property
    def first(self):
        return self

    def is_visible(self, timeout=None):
        return self._vis


class NoNewPage:
    """expect_page: không có tab mới -> ném lỗi khi thoát khối with (giống timeout thật)."""
    def __enter__(self):
        return self

    def __exit__(self, *a):
        raise TimeoutError("no new page")


class Ctx:
    def on(self, *a, **k):
        return None

    def expect_page(self, timeout=None):
        return NoNewPage()


class Keyboard:
    def __init__(self, page):
        self.page = page

    def press(self, key):
        if key == "Enter":
            self.page._nav(SERP_ALL)


class GooglePage:
    """Trang Google giả: tab Tất cả có 3 kết quả thường; tab Tin tức có `news_n` thẻ tin."""
    def __init__(self, news_n, has_news_tab=True, back_mode="ok"):
        self.context = Ctx()
        self.keyboard = Keyboard(self)
        self.url = "about:blank"
        self.hist = []
        self.news_n, self.has_news_tab, self.back_mode = news_n, has_news_tab, back_mode
        self.reloads = 0
        self.gotos = []
        self.backs = 0

    def _nav(self, url):
        self.hist.append(self.url)
        self.url = url

    def goto(self, url, **k):
        self.gotos.append(url)
        self._nav(url)

    def go_back(self, **k):
        self.backs += 1
        if self.back_mode == "stuck" and "google." not in self.url:
            # trang báo đẩy Back về trang chủ của báo + chờ tải quá hạn (đo thật ở lô 19/11)
            self.url = "https://news.example.com/"
            raise TimeoutError("Page.go_back: Timeout 15000ms exceeded")
        if self.hist:
            self.url = self.hist.pop()

    def reload(self, **k):
        self.reloads += 1

    def wait_for_load_state(self, *a, **k):
        return None

    def bring_to_front(self):
        return None

    def locator(self, sel):
        if "has-text('Tin tức')" in sel:
            return Link(self, SERP_NEWS, "tab", vis=self.has_news_tab and self.url == SERP_ALL)
        if sel == NEWS_SEL:
            n = self.news_n if self.url == SERP_NEWS else 0
            return Group([Link(self, f"https://news.example.com/a{i}", "news") for i in range(n)])
        if sel == ORG_SEL:
            n = 3 if self.url == SERP_ALL else 0
            return Group([Link(self, f"https://site.example.com/p{i}", "organic") for i in range(n)])
        return Group([Link(self, "", "box")])


def run(page, n_articles=2):
    wf = WarmupWorkflow(context=page.context, keyword_lang="en")
    wf.rng = random.Random(1)
    clicked = []
    wf.random_sleep = lambda *a, **k: None
    wf.smooth_scroll = lambda *a, **k: None
    wf._smooth_scroll_to_element = lambda *a, **k: None
    wf.move_mouse_viewport_center = lambda *a, **k: None
    wf.restore_mouse_position = lambda *a, **k: None
    wf.enable_virtual_cursor = lambda *a, **k: None
    wf.human_type = lambda *a, **k: None
    wf._refine_search = lambda *a, **k: None
    wf._plan_keyword = lambda *a, **k: "home gym"
    idle = []
    wf._simulate_scroll_and_read = lambda p, a, b: idle.append((a, b))

    def human_click(p, el):
        clicked.append(el.kind)
        p._nav(el.href)
    wf.human_click = human_click
    real_randint = random.randint
    random.randint = lambda a, b: n_articles if (a, b) == (1, 3) else a
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            wf.action_search_and_read_news(page)
    finally:
        random.randint = real_randint
    return buf.getvalue(), clicked, idle


print("\n== 1. Tab Tin tức TRỐNG -> quay lại tab Tất cả, đọc kết quả thường")
pg = GooglePage(news_n=0)
log, clicked, idle = run(pg)
check("nói rõ tab Tin tức trống + quay lại", "Tab Tin tức không có bài nào" in log, log.strip().splitlines()[-1][:80])
check("đọc được bài từ kết quả thường (trước đây 0/2)", "Đã đọc 2/2 bài" in log and clicked == ["tab", "organic", "organic"],
      str(clicked))
check("không còn 'lướt trang trống rồi bỏ đi'", idle == [] and "Không mở được bài nào" not in log)
check("chỉ quay lại tab Tất cả đúng 1 lần", log.count("Tab Tin tức không có bài nào") == 1)
check("kết thúc ở trang kết quả tab Tất cả", pg.url == SERP_ALL, pg.url)

print("\n== 2. Tab Tin tức CÓ bài -> hành vi cũ, không quay lại")
pg = GooglePage(news_n=5)
log, clicked, idle = run(pg)
check("đọc thẻ tin như cũ", "Đã đọc 2/2 bài" in log and clicked == ["tab", "news", "news"], str(clicked))
check("không báo tab trống", "Tab Tin tức không có bài nào" not in log)
check("vẫn ở tab Tin tức", pg.url == SERP_NEWS, pg.url)

print("\n== 3. Google KHÔNG hiện tab Tin tức -> đọc kết quả thường (v1.8.9), không Back oan")
pg = GooglePage(news_n=0, has_news_tab=False)
log, clicked, idle = run(pg, n_articles=1)
check("log v1.8.9 giữ nguyên", "Google không hiện tab Tin tức" in log and "Tab Tin tức không có bài nào" not in log)
check("đọc 1/1 từ kết quả thường", "Đã đọc 1/1 bài" in log and clicked == ["organic"], str(clicked))

print("\n== 4. Back quá hạn + chưa về Google -> KHÔNG tải lại trang báo, mở thẳng lại trang kết quả")
pg = GooglePage(news_n=5, back_mode="stuck")
log, clicked, idle = run(pg, n_articles=2)
check("không Reload trang báo", pg.reloads == 0, f"reloads={pg.reloads}")
check("mở lại đúng trang kết quả đang đọc", pg.gotos.count(SERP_NEWS) == 2, str(pg.gotos))
check("log nói đúng việc đã làm", "Back quá hạn chờ và chưa về Google" in log and "mở lại trang kết quả Google" in log
      and "ép tải lại (Reload)" not in log)
check("vẫn đọc đủ 2/2 bài", "Đã đọc 2/2 bài" in log, str(clicked))

print("\n== 5. Tĩnh")
src_w = open(os.path.join(SRC, "workflow", "warmup.py"), encoding="utf-8").read()
a = src_w.index("def action_search_and_read_news")
news = src_w[a:src_w.index("def move_mouse_bezier", a)]
check("không còn lệnh reload trong hành động", "active_page.reload(" not in news)
check("cờ on_news_tab chỉ bật sau khi bấm tab", "on_news_tab = False" in news and "on_news_tab = True" in news)
check("v1.8.9 còn nguyên: fallback kết quả thường + mở lại serp_url", ORG_SEL in news and "active_page.goto(serp_url" in news
      and "if not _on_serp:" in news)

print("\n== 6. Cổng Google cho Maps: chỉ nhận kết quả của GOOGLE Maps (không đáp nhầm Apple Maps / gymmaps.app)")
import src.workflow.warmup as W  # noqa: E402


class Clock:
    """Đồng hồ giả: mỗi lần hỏi giờ trôi 0,5s -> các vòng 'lướt 15-35s' kết thúc ngay."""
    def __init__(self):
        self.t = 1000.0

    def time(self):
        self.t += 0.5
        return self.t

    def sleep(self, s):
        self.t += s


class Anchor:
    def __init__(self, page, text, href, dest):
        self.page, self.text, self.href, self.dest = page, text, href, dest

    def get_attribute(self, name):
        return self.href

    def inner_text(self, timeout=None):
        return self.text

    def scroll_into_view_if_needed(self, timeout=None):
        return None

    def click(self, timeout=None):
        self.page.clicked.append(self.text)
        self.page.url = self.dest


class Box:
    def wait_for(self, **k):
        return None

    def click(self, **k):
        return None

    @property
    def first(self):
        return self


class SerpCtx:
    def __init__(self, page):
        self.pages = [page]

    def on(self, *a, **k):
        return None


class Serp:
    def __init__(self, rows):
        self.url = "about:blank"
        self.clicked = []
        self.context = SerpCtx(self)
        self.keyboard = type("K", (), {"press": lambda s, k: setattr(self, "url", "https://www.google.com/search?q=x")})()
        self.rows = [Anchor(self, t, h, d) for t, h, d in rows]

    def goto(self, url, **k):
        self.url = url

    def wait_for_load_state(self, *a, **k):
        return None

    def wait_for_timeout(self, ms):
        return None

    def evaluate(self, *a, **k):
        return None

    def locator(self, sel):
        if sel == "a:has(h3)":
            return Group(self.rows)
        return Box()


APPLE = ("MK Fitness in Hoan Kiem | Apple Maps | https://maps.apple.com › place", "/goto?url=AAA", "https://maps.apple.com/place?x")
GYMMAPS = ("99 Fitness: Equipment, Hours | gymmaps.app | https://www.gymmaps.app › gym", "/goto?url=BBB", "https://www.gymmaps.app/gym/9")
GMAPS = ("Gym near me | Google Maps | https://maps.google.com › search", "https://maps.google.com/maps/search/gym+near+me",
         "https://www.google.com/maps/search/gym+near+me")
GOOGL = ("Thế Giới Đồ Tập - Google Maps | goo.gl | https://maps.app.goo.gl › ...", "/goto?url=CCC",
         "https://www.google.com/maps/place/The+Gioi+Do+Tap")


def gateway(rows, must_any):
    pg = Serp(rows)
    wf = WarmupWorkflow(context=pg.context, keyword_lang="en")
    wf.rng = random.Random(2)
    for name in ("random_sleep", "smooth_scroll", "human_type", "move_mouse_bezier", "_pump_wait"):
        setattr(wf, name, lambda *a, **k: None)
    wf._safe_bbox = lambda el, timeout=None: {"x": 10, "y": 10, "width": 300, "height": 40}
    real_time = W.time
    W.time = Clock()
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            ok = wf._navigate_via_google(pg, "gym near me", "maps", must_any=must_any) if must_any is not None \
                else wf._navigate_via_google(pg, "gym near me", "maps")
    finally:
        W.time = real_time
    return ok, pg, buf.getvalue()


MARKS = WarmupWorkflow.MAPS_RESULT_MARKS
ok, pg, log = gateway([APPLE, GYMMAPS], MARKS)
check("chỉ có Apple Maps + gymmaps.app -> không bấm gì, ở lại trang kết quả", ok is False and pg.clicked == []
      and "google.com/search" in pg.url, pg.url)
hits = set()
for seed in range(12):
    random.seed(seed)
    ok, pg, log = gateway([APPLE, GMAPS, GYMMAPS, GOOGL], MARKS)
    hits.add(pg.clicked[0][:14] if pg.clicked else "-")
    if not ok or "google.com/maps" not in pg.url:
        hits.add("SAI:" + pg.url)
check("lẫn 4 loại -> luôn bấm kết quả của Google Maps (12 lượt)", all(h.startswith(("Gym near me", "Thế Giới Đồ T")) for h in hits),
      str(sorted(hits)))
bad = 0
for seed in range(40):
    random.seed(seed)
    ok, pg, log = gateway([APPLE, GMAPS, GYMMAPS, GOOGL], None)
    bad += int("google.com/maps" not in pg.url)
check("đối chứng: không lọc (hành vi cũ) thì có lượt đáp nhầm trang", bad > 0, f"{bad}/40 lượt đáp nhầm")
ok, pg, log = gateway([("Wikipedia | https://en.wikipedia.org › wiki", "/goto?url=W", "https://en.wikipedia.org/wiki/X")], None)
check("site khác (không truyền must_any) không đổi hành vi", ok is False and pg.clicked == [])
m = src_w.index("    def action_search_maps")
maps_src = src_w[m:m + 9000]
check("hành động Maps gọi cổng với bộ lọc Google Maps",
      '_navigate_via_google(page, keyword, "maps", must_any=self.MAPS_RESULT_MARKS)' in maps_src)
check("cổng không ra Maps thì vẫn thử khung bản đồ trước khi vào thẳng",
      maps_src.index("self._serp_open_maps(page)") < maps_src.index("(Fallback Google) vào thẳng"))
check("dấu hiệu Google Maps lấy từ breadcrumb thật", MARKS == ("google maps", "maps.google", "google.com/maps", "maps.app.goo.gl"))

print(f"\nPASS: {PASS}   FAIL: {FAIL}")
print("SMOKE v1.9.0: ALL PASS" if FAIL == 0 else "SMOKE v1.9.0: CO LOI")
sys.exit(0 if FAIL == 0 else 1)
