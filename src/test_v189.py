# -*- coding: utf-8 -*-
"""Smoke test v1.8.9 — LỖI LỘ RA KHI CHẠY LÔ THẬT 4 PROFILE (19/11/2026).

1) Kế hoạch AI: lượt hỏi dài được chờ 40s (trước 10s -> phần lớn rơi về dự phòng)
2) Kế hoạch dự phòng với chủ đề là CẢ CÂU: không ghép mẫu vô nghĩa
3) Kế hoạch chỉ gồm nền tảng phiên đó làm được (tick Bỏ qua YouTube / pha 2 / pha 3)
4) GPM DownloadProfileFailed có lời giải thích

Chạy OFFLINE: python src/test_v189.py
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
os.environ["GPM_BOT_DATA_DIR"] = tempfile.mkdtemp(prefix="gpm_v189_")
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


class Ctx:
    def on(self, *a, **k):
        return None


def make(**kw):
    wf = WarmupWorkflow(context=Ctx(), keyword_lang=kw.pop("lang", "en"), **kw)
    wf.rng = random.Random(3)
    return wf


PLAN_TEXT = ("google | emergency fund basics\nyoutube | emergency fund explained video\nmaps | credit union near me\n"
             "news | savings rates news\nwikipedia | emergency fund\ntiktok | saving money hacks\ngoogle | best savings account")

print("\n== 1. Lượt hỏi kế hoạch được chờ lâu hơn")


class NewBrain:
    def __init__(self):
        self.timeouts = []

    def ask_text(self, prompt, timeout=None):
        self.timeouts.append(timeout)
        return PLAN_TEXT


class OldBrain:
    calls = 0

    def ask_text(self, prompt):
        OldBrain.calls += 1
        return PLAN_TEXT


nb = NewBrain()
wf = make(brain=nb)
plan = wf._safe_ask_plan(topic_hint="how to build an emergency fund")
check("brain mới nhận timeout=40", nb.timeouts == [40], str(nb.timeouts))
check("kế hoạch AI vẫn parse đủ", plan and len(plan) == 7, str(plan and len(plan)))
wf = make(brain=OldBrain())
plan_old = wf._safe_ask_plan(topic_hint="x")
check("brain cũ (không nhận timeout) vẫn chạy", plan_old and len(plan_old) == 7 and OldBrain.calls == 1)

import src.agent.openai_brain as ob  # noqa: E402

seen = {}


class FakeCompletions:
    def create(self, **k):
        seen["timeout"] = k.get("timeout")
        msg = type("M", (), {"content": " ok "})()
        return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()


fake_client = type("Cl", (), {"chat": type("Ch", (), {"completions": FakeCompletions()})()})()
gb = ob.GenericLLMBrain.__new__(ob.GenericLLMBrain)
gb.model_name = "m"
gb._keys = ["k"]
gb.client = fake_client
check("GenericLLMBrain: mặc định vẫn 10s", gb.ask_text("p") == "ok" and seen["timeout"] == 10, str(seen))
gb.ask_text("p", timeout=40)
check("GenericLLMBrain: timeout=40 tới đúng lệnh gọi API", seen["timeout"] == 40, str(seen))

print("\n== 2. Kế hoạch dự phòng với chủ đề là cả câu")
BAD = ("best how to", "gear to buy", "to lose weight", "weather today", "how to how to", "shop near me", "tutorial for beginners")
for topic in ("how to build an emergency fund", "healthy meal prep grocery list budget", "stress relief classes near me"):
    wf = make()
    wf.related_keywords = ["best budgeting apps comparison 2024", "high yield savings account", "side hustle ideas for beginners"]
    steps = wf._local_plan_steps(topic)
    qs = [s["query"] for s in steps]
    check(f"'{topic[:28]}…': không câu ghép vô nghĩa", not any(b in q for q in qs for b in BAD if b not in topic),
          str([q for q in qs if any(b in q for b in BAD if b not in topic)]))
    check(f"'{topic[:28]}…': mở màn bằng đúng chủ đề trên Google", steps[0] == {"platform": "google", "query": topic})
    check(f"'{topic[:28]}…': đủ 6-12 bước, có từ khóa liên quan", 6 <= len(steps) <= 12
          and "high yield savings account" in qs, f"n={len(steps)}")
wf = make()
maps_steps = [s for s in wf._local_plan_steps("stress relief classes near me") if s["platform"] == "maps"]
check("chủ đề có 'near me' -> có bước Maps; chủ đề khác thì không ép Maps",
      len(maps_steps) == 1 and not [s for s in make()._local_plan_steps("how to build an emergency fund") if s["platform"] == "maps"])
short = make()._local_plan_steps("walking")
check("chủ đề NGẮN giữ nguyên cách cũ (mẫu ghép, đủ 6 nền tảng)",
      6 <= len(short) <= 10 and {s["platform"] for s in short} >= {"google", "youtube", "maps", "news", "wikipedia", "tiktok"})
check("nhận diện chủ đề cả câu", WarmupWorkflow._topic_is_specific("how to build an emergency fund")
      and not WarmupWorkflow._topic_is_specific("home workout") and WarmupWorkflow._topic_is_specific("ウォーキングシューズおすすめ")
      and not WarmupWorkflow._topic_is_specific("ランニング"))

print("\n== 3. Kế hoạch chỉ gồm nền tảng phiên đó làm được")
check("mặc định: đủ 6 nền tảng, đúng thứ tự cũ",
      make()._plan_platforms() == ["google", "youtube", "maps", "news", "wikipedia", "tiktok"])
check("tick Bỏ qua YouTube -> không youtube", "youtube" not in make(skip_youtube=True)._plan_platforms())
check("pha 2 (mail) -> không youtube", "youtube" not in make(phase="mail")._plan_platforms())
check("pha 3 (youtube) -> không tiktok, có youtube",
      "tiktok" not in make(phase="youtube")._plan_platforms() and "youtube" in make(phase="youtube")._plan_platforms())


class SpyBrain:
    prompt = ""

    def ask_text(self, prompt, timeout=None):
        SpyBrain.prompt = prompt
        return PLAN_TEXT


wf = make(brain=SpyBrain(), skip_youtube=True)
plan = wf._safe_ask_plan(topic_hint="how to build an emergency fund")
check("prompt không mời AI dùng youtube", "one of: google, maps, news, wikipedia, tiktok." in SpyBrain.prompt, SpyBrain.prompt[-260:-150])
check("AI vẫn trả bước youtube -> đổi thành tìm Google, giữ từ khóa",
      plan and all(s["platform"] != "youtube" for s in plan)
      and {"platform": "google", "query": "emergency fund explained video"} in plan, str(plan))
loc = make(skip_youtube=True)._local_plan_steps("walking")
check("dự phòng + Bỏ qua YouTube -> không còn bước youtube chết", all(s["platform"] != "youtube" for s in loc))

import src.ui_main as ui  # noqa: E402

sys.stdout = sys.__stdout__
p_skip, src_skip = ui.build_session_plan("walking", [], "none", "en", "clean", True)
p_norm, _ = ui.build_session_plan("walking", [], "none", "en")
check("build_session_plan nhận phase + skip_youtube", all(s["platform"] != "youtube" for s in p_skip)
      and any(s["platform"] == "youtube" for s in p_norm))
src_u = open(os.path.join(SRC, "ui_main.py"), encoding="utf-8").read()
check("start_automation truyền pha + Bỏ qua YouTube vào khâu sinh kế hoạch",
      'self._plan_preview, PHASE_MAP.get(self.var_phase_label.get(), "clean"),' in src_u
      and "bool(self.var_skip_youtube.get()))," in src_u)

print("\n== 4. GPM DownloadProfileFailed có lời giải thích")
from src.browser.antidetect import AntidetectAPI  # noqa: E402
import src.browser.antidetect as ad  # noqa: E402


class Resp:
    status_code = 200

    def json(self):
        return {"success": False, "data": {}, "message": "DownloadProfileFailed"}

    def raise_for_status(self):
        pass


real_get = ad.requests.get
ad.requests.get = lambda *a, **k: Resp()
try:
    api = AntidetectAPI("http://localhost:1")
    ws = api.open_profile("PID")
finally:
    ad.requests.get = real_get
check("trả None + giải thích cách xử lý", ws is None and "DownloadProfileFailed" in (api.last_error or "")
      and "bằng tay" in api.last_error, str(api.last_error)[:90])

print("\n== 5. Trình duyệt chết giữa phiên -> kết thúc phiên ngay (không chạy 'xác sống')")
import contextlib  # noqa: E402
import io as _io  # noqa: E402
import src.workflow.warmup as W  # noqa: E402


class DeadablePage:
    def __init__(self):
        self.closed = False
        self.url = "about:blank"

    def is_closed(self):
        return self.closed

    def close(self):
        self.closed = True


class RunCtx:
    def __init__(self):
        self.page = DeadablePage()

    def on(self, *a, **k):
        return None

    def new_page(self):
        return self.page


check("_browser_gone: page giả không có is_closed -> False", WarmupWorkflow._browser_gone(object()) is False)
dp = DeadablePage()
check("_browser_gone: tab còn sống -> False", WarmupWorkflow._browser_gone(dp) is False)
dp.closed = True
check("_browser_gone: tab đã đóng -> True", WarmupWorkflow._browser_gone(dp) is True)
BrDead = type("B", (), {"is_connected": lambda self: False})
pg2 = type("P", (), {"is_closed": lambda self: False, "context": type("C", (), {"browser": BrDead()})()})()
check("_browser_gone: trình duyệt mất kết nối -> True", WarmupWorkflow._browser_gone(pg2) is True)

real_rest = W._sample_action_rest
W._sample_action_rest = lambda *a, **k: 0
try:
    rc = RunCtx()
    wf = WarmupWorkflow(context=rc, keyword_lang="en")
    wf.session_deadline_s = 3600
    wf.enable_virtual_cursor = lambda page: None
    ran = []
    NAMES = ["action_read_news", "action_read_world_news", "action_search_and_read_news", "action_search_weather",
             "action_google_finance", "action_watch_tiktok", "action_read_wikipedia", "action_search_maps",
             "action_watch_video", "action_search_youtube"]

    def mk(name):
        def act(page):
            ran.append(name)
            if len(ran) == 2:
                page.closed = True   # trình duyệt bị đóng trong lúc làm hành động thứ 2
        return act
    for n_ in NAMES:
        setattr(wf, n_, mk(n_))
    err = None
    with contextlib.redirect_stdout(_io.StringIO()):
        try:
            wf.run_random_session(total_actions=8)
        except RuntimeError as e:
            err = str(e)
    check("phiên dừng ngay sau hành động làm chết trình duyệt (2/8)", len(ran) == 2, str(len(ran)))
    check("ném lỗi rõ ràng để chu trình ghi 'error'", bool(err) and "đã bị đóng" in err, str(err))
finally:
    W._sample_action_rest = real_rest

print("\n== 6. Watchdog giải cứu slot treo")
for d in (ui.SLOT_THREAD_ALIVE, ui.SLOT_API, ui.SLOT_LAST_LOG):
    d.clear()
ui._WATCHDOG_DONE.clear()
closed = []


class WApi:
    def close_profile(self, pid):
        closed.append(pid)


now = 1_000_000.0
ui.SLOT_THREAD_ALIVE.update({"Slot 1": True, "Slot 2": True, "Slot 3": False})
ui.SLOT_API.update({"Slot 1": (WApi(), "PID-TREO-1"), "Slot 2": (WApi(), "PID-OK-2"), "Slot 3": (WApi(), "PID-XONG-3")})
ui.SLOT_LAST_LOG.update({"Slot 1": now - 1000, "Slot 2": now - 500, "Slot 3": now - 5000})
run_now = lambda fn: fn()  # noqa: E731
with contextlib.redirect_stdout(_io.StringIO()) as wout:
    hits = ui.watchdog_rescue(now, spawn=run_now)
check("ngưỡng 15 phút (> nhịp nghỉ dài nhất 8 phút)", ui.WATCHDOG_SILENT_S == 900)
check("chỉ slot đang chạy + im lặng > 15 phút bị đóng", closed == ["PID-TREO-1"] and [h[0] for h in hits] == ["Slot 1"], str(closed))
check("có log nói rõ lý do", "[Watchdog] Slot 1 (PID-TREO" in wout.getvalue() and "TREO" in wout.getvalue())
with contextlib.redirect_stdout(_io.StringIO()):
    ui.watchdog_rescue(now + 60, spawn=run_now)
check("không đóng lặp lại cùng profile", closed == ["PID-TREO-1"])
src_u2 = open(os.path.join(SRC, "ui_main.py"), encoding="utf-8").read()
check("worker đăng ký/dọn SLOT_API + _tick_status gọi watchdog",
      "SLOT_API[slot_key] = (api, profile_id)" in src_u2 and "SLOT_API.pop(slot_key, None)" in src_u2
      and "watchdog_rescue()" in src_u2[src_u2.index("def _tick_status"):src_u2.index("def _create_tab")])
for d in (ui.SLOT_THREAD_ALIVE, ui.SLOT_API, ui.SLOT_LAST_LOG):
    d.clear()

print("\n== 7. Số hành động thật + không mở bài mới khi hết giờ phiên")
import time as _time  # noqa: E402

W._sample_action_rest = lambda *a, **k: 0
try:
    rc = RunCtx()
    wf = WarmupWorkflow(context=rc, keyword_lang="en")
    wf.session_deadline_s = 3600
    wf.enable_virtual_cursor = lambda page: None
    for n_ in NAMES:
        setattr(wf, n_, lambda page: None)
    with contextlib.redirect_stdout(_io.StringIO()):
        wf.run_random_session(total_actions=5)
    check("actions_done = số hành động đã chạy thật", wf.actions_done == 5, str(wf.actions_done))
finally:
    W._sample_action_rest = real_rest
wf = make()
check("_session_time_up: chưa đặt mốc -> False", wf._session_time_up() is False)
wf._session_end_ts = _time.time() - 1
check("_session_time_up: quá mốc -> True", wf._session_time_up() is True)
wf._session_end_ts = _time.time() + 600
check("_session_time_up: còn giờ -> False", wf._session_time_up() is False)
src_w = open(os.path.join(SRC, "workflow", "warmup.py"), encoding="utf-8").read()
check("2 hành động đọc nhiều bài đều kiểm giờ trước bài kế", src_w.count("self._session_time_up():") >= 2)

# đồng hồ giả: mỗi hành động "tốn" 100s; trần phiên 200s -> sau hành động 1 còn 100s (< 150s) => không mở hành động 2
clock = [5000.0]
real_time_fn, real_sleep_fn = _time.time, _time.sleep
W._sample_action_rest = lambda *a, **k: 0
_time.time = lambda: clock[0]
_time.sleep = lambda s_=0: clock.__setitem__(0, clock[0] + max(0.0, s_))
try:
    rc = RunCtx()
    wf = WarmupWorkflow(context=rc, keyword_lang="en")
    wf.session_deadline_s = 200
    wf.enable_virtual_cursor = lambda page: None
    for n_ in NAMES:
        setattr(wf, n_, lambda page: clock.__setitem__(0, clock[0] + 100))
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        wf.run_random_session(total_actions=6)
    done_short = wf.actions_done
    log_short = buf.getvalue()
finally:
    _time.time, _time.sleep = real_time_fn, real_sleep_fn
    W._sample_action_rest = real_rest
check("còn < 2,5 phút -> không mở hành động mới (không lố trần)", done_short == 1 and "không mở hành động mới" in log_short,
      f"done={done_short}")
check("ngưỡng: MIN_ACTION_LEFT_S=150, READ_OVERRUN_S=45",
      WarmupWorkflow.MIN_ACTION_LEFT_S == 150 and WarmupWorkflow.READ_OVERRUN_S == 45)
rd = src_w[src_w.index("def _simulate_scroll_and_read"):][:1400]
check("lượt đọc rút gọn khi phiên sắp hết giờ", "cap = max(30, int(end_ts - time.time()) + self.READ_OVERRUN_S)" in rd
      and "read_time_seconds = cap" in rd)
check("ui ghi số hành động thật vào chu trình", '_done = getattr(warmup, "actions_done", None)' in src_u2)

print("\n== 8. Tìm Google -> Tin tức: không còn 'tìm xong bỏ đi' + log trung thực")
a = src_w.index("def action_search_and_read_news")
news = src_w[a:src_w.index("def move_mouse_bezier", a)]
check("không có tab Tin tức -> nói rõ + đọc kết quả thường", "Google không hiện tab Tin tức" in news
      and '"#rso a:has(h3), #search a:has(h3)"' in news)
check("bỏ selector 'a h3' (thẻ h3 không có href nên luôn bị loại)", "a.WlydOe, a h3" not in news)
check("log đếm số bài ĐỌC THẬT", "Đã đọc {read_count}/{num_articles_to_read} bài" in news and "Đã xử lý" not in news)
check("0 bài -> lướt đọc trang kết quả, không rời đi ngay", "if read_count == 0:" in news
      and "self._simulate_scroll_and_read(active_page, 25, 60)" in news)
check("Back không về Google -> mở lại đúng trang kết quả", "active_page.goto(serp_url" in news)
check("đã về Google thì không Reload vô cớ", "if not _on_serp:" in news)

print("\n== 9. Google Maps: bấm khung bản đồ địa điểm trên trang kết quả")


class El:
    def __init__(self, href, page):
        self.href, self.page = href, page

    def get_attribute(self, name, timeout=0):
        return self.href

    def click(self, timeout=0):
        self.page.clicked.append(self.href)
        self.page.url = "https://www.google.com" + self.href if self.href.startswith("/") else self.href


class SerpPage:
    def __init__(self, hrefs, url="https://www.google.com/search?q=yoga+near+me+maps"):
        self.url = url
        self.clicked = []
        self.els = [El(h, self) for h in hrefs]

    def locator(self, sel):
        return type("L", (), {"all": lambda s, _e=self.els: list(_e)})()

    def wait_for_timeout(self, ms):
        pass


def maps_wf():
    w = make()
    w._safe_bbox = lambda el, timeout=0: {"x": 10, "y": 300, "width": 190, "height": 160}
    w._smooth_scroll_to_element = lambda page, el: None
    w.move_mouse_bezier = lambda page, el: None
    w.random_sleep = lambda *a: None
    return w


sp = SerpPage(["https://maps.google.com/maps/search/yoga+near+vietnam", "/maps/place/Asoka+Yoga/data=!4m2"])
with contextlib.redirect_stdout(_io.StringIO()):
    ok_maps = maps_wf()._serp_open_maps(sp)
check("ưu tiên link ĐỊA ĐIỂM, sang được Maps", ok_maps is True and sp.clicked == ["/maps/place/Asoka+Yoga/data=!4m2"], str(sp.clicked))
sp2 = SerpPage([])
check("không có khung bản đồ -> False (để fallback như cũ)", maps_wf()._serp_open_maps(sp2) is False)
sp3 = SerpPage(["/maps/place/X"], url="https://www.bbc.com/news")
check("không ở trang kết quả Google -> không bấm gì", maps_wf()._serp_open_maps(sp3) is False and not sp3.clicked)
m = src_w.index("    def action_search_maps")
maps_src = src_w[m:src_w.index("    def ", m + 40) if False else m + 9000]
check("thử khung bản đồ TRƯỚC khi vào thẳng", maps_src.index("self._serp_open_maps(page)") < maps_src.index("(Fallback Google) vào thẳng"))
check("ở trang địa điểm: không gọi _close_popups (nó bấm nút Đóng của bảng địa điểm), không gõ đè",
      "if not on_place:\n                self._close_popups(page)" in maps_src.replace("\r\n", "\n")
      and "opened_place = on_place" in maps_src)

print(f"\nPASS: {PASS}   FAIL: {FAIL}")
print("SMOKE v1.8.9: ALL PASS" if FAIL == 0 else "SMOKE v1.8.9: CO LOI")
sys.exit(0 if FAIL == 0 else 1)
