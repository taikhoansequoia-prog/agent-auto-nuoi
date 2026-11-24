# -*- coding: utf-8 -*-
"""
Smoke test v1.9.5 — PHIÊN NGÂM KÊNH TÍNH THEO ĐỘ DÀI VIDEO ĐỐI THỦ.

Chạy:  python test_v195.py
Cô lập: GPM_BOT_DATA_DIR + GPM_BOT_ENV_FILE -> temp (hash DB/config/.env thật trước == sau). Không gọi mạng/trình duyệt.

Phủ:
  [1] Hàm thuần: median_len, plan_session (video ngắn/vừa/dài/rất dài, trần cứng), session_range_min
  [2] normalize_niche: số user nhập > số học qua API > chưa biết
  [3] Phiên giả lập: biết sẵn độ dài -> lập kế hoạch ngay; chưa biết -> đo ở lần tìm đầu; caller ghim trần -> giữ nguyên;
      hạn mức ngày (channel_max_s) là trần cứng; không đo được -> giữ SOP 45–60 phút
  [4] _ch_watch dùng trần xem của kế hoạch; chọn video xem sâu theo khoảng độ dài của phiên
  [5] niche_learner ghi typical_len_s + báo cáo
  [6] UI: ô 'Video đối thủ dài' (lưu / kiểm tra / nạp lại), run_single_profile đưa hạn mức còn lại làm trần cứng
"""
import hashlib
import os
import random
import sys
import tempfile
import time
import tkinter as tk
from tkinter import ttk

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for p in (REPO, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TMP = tempfile.mkdtemp(prefix="gpm_v195_")
DATA_DIR = os.path.join(TMP, "data")
os.makedirs(DATA_DIR, exist_ok=True)
ENV_FILE = os.path.join(TMP, ".env")
open(ENV_FILE, "w", encoding="utf-8").write("")
REAL = [os.path.join(REPO, "data", "agent_logs.db"), os.path.join(REPO, "data", "app_config.json"),
        os.path.join(REPO, ".env")]


def _hash(path):
    try:
        return hashlib.sha256(open(path, "rb").read()).hexdigest()
    except Exception:
        return None


BEFORE = {p: _hash(p) for p in REAL}
os.environ["GPM_BOT_DATA_DIR"] = DATA_DIR
os.environ["GPM_BOT_ENV_FILE"] = ENV_FILE

from src.workflow import channel_mode as cm  # noqa: E402
from src.workflow import niche_learner as nl  # noqa: E402
from src.workflow.warmup import WarmupWorkflow  # noqa: E402
from src import app_config  # noqa: E402
from src import ui_main as ui  # noqa: E402

# brain_manager gọi load_dotenv() lúc import -> key YouTube trong .env THẬT lọt vào os.environ của tiến trình test.
for _k in [k for k in os.environ if k.startswith("YOUTUBE_API_KEY")]:
    os.environ.pop(_k, None)

PASS = FAIL = 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {extra}")


M = 60
# ---------------------------------------------------------------- [1]
print("\n[1] Ham thuan")
check("median_len le / chan", cm.median_len([600, 900, 1200]) == 900 and cm.median_len([600, 900, 1200, 1500]) == 1050)
check("median_len bo Shorts (<3 phut) + 0/None", cm.median_len([30, 45, 0, None, 600, 900, 1200]) == 900)
check("median_len it hon 3 mau -> 0", cm.median_len([600, 900]) == 0 and cm.median_len([]) == 0 and cm.median_len(None) == 0)
random.seed(5)
for mins in (4, 8, 10, 15, 20, 30, 45, 60, 90, 180):
    for n0 in (3, 4, 5):
        p = cm.plan_session(mins * M, n0)
        ok = (min(cm.SESSION_MIN_S, cm.SESSION_MAX_S) <= p["session_s"] <= cm.SESSION_MAX_S and 3 <= p["n_long"] <= 8
              and p["deep_cap_s"] >= 180 and p["mid_cap_s"] >= 120 and p["est_s"] <= p["session_s"] + 1)
        if not ok:
            check(f"plan_session({mins} phut, n={n0}) hop le", False, str(p))
            break
    else:
        continue
    break
else:
    check("plan_session: moi do dai deu cho phien 45-150 phut, 3-8 video, uoc luong <= tran", True)
p10, p30, p60 = (cm.plan_session(m * M, 4, 0, cm._MidRng) for m in (10, 30, 60))
check("video dai hon -> phien dai hon", p10["session_s"] < p30["session_s"] <= p60["session_s"],
      f"{p10['session_s']} {p30['session_s']} {p60['session_s']}")
check("video 10 phut: van quanh SOP 45-65 phut, tran xem sau >= 12 phut", 45 * M <= p10["session_s"] <= 65 * M and p10["deep_cap_s"] >= 720)
check("video 30 phut: xem sau du 70-90% (tran >= 27 phut), video sau du 50-60% (tran >= 18 phut)",
      p30["deep_cap_s"] >= 27 * M and p30["mid_cap_s"] >= 18 * M and not p30["squeezed"], str(p30))
p4 = cm.plan_session(4 * M, 3, 0, cm._MidRng)
check("video ngan 4 phut: them video cho du ~45 phut", p4["n_long"] >= 6 and p4["session_s"] >= 45 * M, str(p4))
p180 = cm.plan_session(180 * M, 5, 0, cm._MidRng)
check("video rat dai: khong qua 150 phut, con 3 video, ha muc xem", p180["session_s"] == cm.SESSION_MAX_S and p180["n_long"] == 3
      and p180["squeezed"] and p180["deep_cap_s"] <= 75 * M, str(p180))
pc = cm.plan_session(30 * M, 5, 50 * M, cm._MidRng)
check("tran cung 50 phut voi video 30 phut: vua khit, bot video + ha muc xem",
      pc["session_s"] == 50 * M and pc["n_long"] == 3 and pc["squeezed"] and pc["est_s"] <= 50 * M, str(pc))
pt = cm.plan_session(15 * M, 4, 10 * M, cm._MidRng)
check("tran cung rat nho (10 phut) khong vo", pt["session_s"] == 10 * M and pt["deep_cap_s"] >= 180)
check("fit: khoang do dai uu tien cho video xem sau bao quanh do dai dien hinh",
      p30["fit"][0] <= 30 * M <= p30["fit"][1] and p30["fit"][0] >= 15 * M and p10["fit"] == (300, 1500), str(p30["fit"]))
check("do dai 0/None -> coi nhu 3 phut, khong vo", cm.plan_session(0)["typical_s"] == 180 and cm.plan_session(None)["n_long"] >= 3)
lo, hi = cm.session_range_min(20 * M)
check(f"session_range_min(20 phut) = {lo}-{hi} phut", 55 <= lo < hi <= 110)
check("session_range_min ton trong tran cung", cm.session_range_min(40 * M, 60 * M) == (60, 60))

# ---------------------------------------------------------------- [2]
print("\n[2] normalize_niche")
RAW = {"name": "Deep sea", "keywords": ["mariana trench documentary", "deep sea creatures", "ocean trench animals"],
       "channels": ["@OceanDiscover"], "negative": [], "groups": [], "sync_locale": True}
n0 = cm.normalize_niche(RAW)
check("chua biet do dai -> 0", n0["typical_len_s"] == 0 and n0["typical_src"] == "")
n1 = cm.normalize_niche(dict(RAW, learned={"typical_len_s": 1500}))
check("hoc qua API -> 25 phut", n1["typical_len_s"] == 1500 and "học" in n1["typical_src"])
n2 = cm.normalize_niche(dict(RAW, video_minutes=12, learned={"typical_len_s": 1500}))
check("so user nhap thang so hoc qua API", n2["typical_len_s"] == 720 and n2["typical_src"] == "bạn nhập")
check("nhap kieu chuoi '12,5' van doc duoc", cm.normalize_niche(dict(RAW, video_minutes="12,5"))["typical_len_s"] == 750)
check("gia tri hong khong lam vo", cm.normalize_niche(dict(RAW, video_minutes="abc", learned={"typical_len_s": "x"}))["typical_len_s"] == 0)

# ---------------------------------------------------------------- [3]
print("\n[3] Phien gia lap")


class FakePage:
    def __init__(self):
        self.url, self.closed = "about:blank", False

    def close(self):
        self.closed = True

    def is_closed(self):
        return False

    def title(self):
        return "Fake video - YouTube"


class FakeContext:
    def __init__(self):
        self.pages = []

    def on(self, *_a, **_k):
        pass

    def new_page(self):
        pg = FakePage()
        self.pages.append(pg)
        return pg


class FakeDB:
    def __init__(self):
        self.logged = []

    def count_activity(self, pid, action, days=1):
        return 0

    def can_subscribe_today(self, pid):
        return True

    def get_keyword_last_used(self, pid, kws=None):
        return {}

    def log_keyword_used(self, pid, kw):
        return True

    def log_activity(self, pid, action, platform="", url="", title="", status="ok", duration_s=None, error=None):
        self.logged.append((action, platform, title, status))
        return True


def make_session(niche, deadline=0, row_dur=900, max_s=0):
    w = WarmupWorkflow(context=FakeContext(), phase="channel", profile_id="P-S", db_handler=FakeDB())
    w.niche = dict(niche)
    w.session_deadline_s = deadline
    if max_s:
        w.channel_max_s = max_s
    ev = []
    w.enable_virtual_cursor = lambda page: None
    w._ch_goto = lambda page, url: None
    w._pump_wait = lambda page, s: None
    w._close_popups = lambda page: None
    w._ch_rest = lambda page, lo, hi: None
    w._browser_gone = lambda page: False
    w._ch_sync_locale = lambda page: {"GL": "US", "HL": "en", "LOGGED_IN": False}
    w._ch_cross_signal = lambda page, q: False
    w._ch_search = lambda page, kw, use_filter: (ev.append(("search", kw)) or use_filter)

    def _rows(page, n):
        k = sum(1 for e in ev if e[0] == "search")
        durs = row_dur if isinstance(row_dur, list) else [row_dur] * 6
        return [{"idx": i, "title": f"Mariana Trench documentary part {k}-{i}", "chan": "Ocean Discover", "views": 5,
                 "age_h": 30.0, "vph": 1000.0 + i, "dur_s": d, "score": 8, "why": "t"} for i, d in enumerate(durs)]
    w._ch_read_results = _rows
    w._ch_open_search_result = lambda page, row: True
    w._ch_watch = lambda page, role, in_niche=True: (ev.append(("watch", role, dict(w._ch_sess or {}))) or
                                                     {"title": f"w{len(ev)}", "watched_s": 1, "ratio": 0.8})
    w._ch_shorts = lambda page: 2
    w._ch_home_training = lambda page, n, seen: 1
    return w, ev


random.seed(7)
w, ev = make_session(dict(RAW, video_minutes=30))
w.run_channel_session()
watches = [e for e in ev if e[0] == "watch"]
check("biet san 30 phut: ke hoach co tu dau phien, tran xem sau >= 27 phut",
      watches and watches[0][2].get("deep_cap_s", 0) >= 27 * M and w._ch_sess["typical_s"] == 1800)
check("biet san 30 phut: tran phien 70-150 phut (khong con co dinh 45-60)", 70 * M <= w.session_deadline_s <= 150 * M,
      str(w.session_deadline_s / 60))
check("so video dai dung theo ke hoach", len(watches) == w._ch_sess["n_long"], f"{len(watches)} vs {w._ch_sess}")

w, ev = make_session(RAW, row_dur=[1200, 1500, 1800, 2400, 40, 55])
w.run_channel_session()
watches = [e for e in ev if e[0] == "watch"]
check("chua biet: do tren trang ket qua (bo Shorts) -> trung vi 27.5 phut", w._ch_sess and w._ch_sess["typical_s"] == 1650,
      str(w._ch_sess))
check("do xong TRUOC khi xem video dau tien", watches[0][2].get("typical_s") == 1650)
check("phien duoc keo dai theo do dai do duoc", w.session_deadline_s > 60 * M, str(w.session_deadline_s / 60))

w, ev = make_session(RAW, row_dur=[40, 50, 0, 0, 600, 0])
w.run_channel_session()
check("khong du mau de do -> giu SOP 45-60 phut, khong co ke hoach", w._ch_sess is None and 45 * M <= w.session_deadline_s <= 60 * M)
check("khong do duoc van xem 3-5 video", 3 <= len([e for e in ev if e[0] == "watch"]) <= 5)

w, ev = make_session(dict(RAW, video_minutes=30), deadline=40 * M)
w.run_channel_session()
check("caller ghim tran 40 phut -> giu nguyen 40 phut", w.session_deadline_s == 40 * M)
check("ke hoach tu co lai cho vua tran da ghim", w._ch_sess["squeezed"] and w._ch_sess["est_s"] <= 40 * M and w._ch_sess["n_long"] == 3,
      str(w._ch_sess))

w, ev = make_session(dict(RAW, video_minutes=40), max_s=70 * M)
w.run_channel_session()
check("han muc ngay con 70 phut la tran cung cua phien dai", w.session_deadline_s <= 70 * M and w._ch_sess["est_s"] <= 70 * M,
      str(w.session_deadline_s / 60))
w, ev = make_session(RAW, row_dur=[40, 50], max_s=50 * M)
w.run_channel_session()
check("chua do duoc + han muc 50 phut -> khong vuot 50 phut", w.session_deadline_s <= 50 * M)

# ---------------------------------------------------------------- [4]
print("\n[4] _ch_watch + chon video theo ke hoach")
w = WarmupWorkflow(context=FakeContext(), phase="channel", profile_id="P-W", db_handler=FakeDB())
rows = [{"idx": i, "title": f"t{i}", "chan": "c", "vph": 100.0 - i, "dur_s": d, "score": 8, "why": ""}
        for i, d in enumerate([400, 700, 2000, 2400, 9000])]
random.seed(1)
w._ch_sess = None
picked = {w._ch_choose_result(rows, True, set())[0]["dur_s"] for _ in range(60)}
check("chua co ke hoach: video xem sau uu tien 6-25 phut nhu cu", picked <= {400, 700})
w._ch_sess = cm.plan_session(35 * M, 4)
picked = {w._ch_choose_result(rows, True, set())[0]["dur_s"] for _ in range(60)}
check("niche video 35 phut: video xem sau lay trong khoang 17-56 phut", picked <= {2000, 2400}, str(picked))
picked = {w._ch_choose_result(rows, False, set())[0]["dur_s"] for _ in range(60)}
check("video xem trung binh khong bi gioi han do dai", len(picked) >= 3)

said = []
w._ch_say = said.append
w._ch_handle_ads = lambda page, max_s=90: None
w._ch_ensure_playing = lambda page, quiet=False: None
w._ch_ensure_audio = lambda page: None
w._ch_fidget = lambda page: None
w.random_sleep = lambda a, b: None
w._browser_gone = lambda page: False
w._parse_time = lambda t: 2400
w._ch_plan = {}


class _Loc:
    first = None

    def inner_text(self, timeout=0):
        return "40:00"


_Loc.first = _Loc()


class WatchPage(FakePage):
    def wait_for_load_state(self, *a, **k):
        pass

    def locator(self, sel):
        return _Loc()


def run_watch(role):
    said.clear()
    w._session_end_ts = time.time() + 5 * 3600
    _real_sleep, _real_time = time.sleep, time.time
    clock = {"t": _real_time()}
    time.sleep = lambda s: clock.__setitem__("t", clock["t"] + s)
    time.time = lambda: clock["t"]
    try:
        return w._ch_watch(WatchPage(), role, in_niche=True)
    finally:
        time.sleep, time.time = _real_sleep, _real_time


w._ch_sess = None
r = run_watch("deep")
check("khong co ke hoach: video 40 phut bi bo do o tran 12-18 phut", r and 12 * M - 10 <= r["watched_s"] <= 18 * M + 10, str(r))
w._ch_sess = cm.plan_session(40 * M, 4)
r = run_watch("deep")
check("co ke hoach (video doi thu 40 phut): xem sau du 70-90% = 28-36 phut", r and 28 * M - 10 <= r["watched_s"] <= 36 * M + 10
      and "chạm trần" not in said[0], f"{r} {said[:1]}")
r = run_watch("mid")
check("co ke hoach: video sau xem 50-60% = 20-24 phut", r and 20 * M - 10 <= r["watched_s"] <= 24 * M + 10, str(r))
w._ch_sess = cm.plan_session(10 * M, 4)
r = run_watch("deep")
check("niche video 10 phut gap video 40 phut: van bo do (tran ~12 phut)", r and r["watched_s"] <= 12 * M + 10 and "chạm trần" in said[0])

# ---------------------------------------------------------------- [5]
print("\n[5] niche_learner")


def _v(i, dur):
    return {"id": f"v{i}", "title": f"Anglerfish dive {i}", "tags": [], "views": 1000, "comments": 0, "duration_s": dur,
            "vph": 1.0, "channel": "C", "channel_id": "UC1"}


_orig = (nl.resolve_channel, nl.fetch_channel_videos, nl.fetch_comments)
nl.resolve_channel = lambda api, raw: {"id": "UC1", "title": "C", "uploads": "UU1", "subs": 1, "video_count": 6}
nl.fetch_comments = lambda api, vid, limit=30: []
nl.fetch_channel_videos = lambda api, ch, limit=30, now=None: [_v(i, d) for i, d in enumerate([45, 50, 1200, 1500, 1800, 2100])]
L = nl.learn_niche(RAW, ["K"], http=lambda p, q: (200, {}))
check("learned co typical_len_s = trung vi video dai (bo Shorts)", L["typical_len_s"] == 1650 and L["long_videos"] == 4, str(L.get("typical_len_s")))
rep = nl.format_report(L)
check("bao cao noi ro do dai + do dai phien", "ĐỘ DÀI VIDEO ĐỐI THỦ: khoảng 28 phút" in rep and "mỗi phiên ngâm sẽ dài khoảng" in rep, rep[:300])
nl.fetch_channel_videos = lambda api, ch, limit=30, now=None: [_v(i, d) for i, d in enumerate([45, 50, 55])]
L2 = nl.learn_niche(RAW, ["K"], http=lambda p, q: (200, {}))
check("kenh chi co Shorts -> typical 0 + bao 'tu do'", L2["typical_len_s"] == 0 and "tự đo" in nl.format_report(L2))
nl.resolve_channel, nl.fetch_channel_videos, nl.fetch_comments = _orig
check("niche da hoc -> phien dung so do", cm.normalize_niche(dict(RAW, learned=L))["typical_len_s"] == 1650)

# ---------------------------------------------------------------- [6]
print("\n[6] Giao dien")
root = tk.Tk()
root.geometry("1200x820+0+0")
app = ui.AutomationApp(root)
root.update()


def walk(wd):
    yield wd
    for c in wd.winfo_children():
        yield from walk(c)


app.cfg["niches"] = [dict(RAW)]
app.open_niche_manager()
root.update()
nd = app._niche_dialog
entries = [x for x in walk(nd) if isinstance(x, ttk.Entry)]
buttons = {str(b.cget("text")): b for b in walk(nd) if isinstance(b, ttk.Button)}
status = [x for x in walk(nd) if isinstance(x, tk.Label)][-1]
ent_len = entries[4]
check("form co o 'Video doi thu dai' (o thu 5, truoc o key)", len(entries) == 7
      and any("Video đối thủ dài" in str(x.cget("text")) for x in walk(nd) if isinstance(x, tk.Label)))
check("niche chua nhap -> o trong", ent_len.get() == "")
ent_len.insert(0, "abc")
buttons["Lưu niche"].invoke()
check("nhap chu -> tu choi luu", "phải là số phút" in status.cget("text") and "video_minutes" not in app.cfg["niches"][0])
ent_len.delete(0, "end")
ent_len.insert(0, "22,5")
buttons["Lưu niche"].invoke()
root.update()
saved = app_config.load_config()["niches"][0]
check("luu 22,5 phut vao app_config", saved.get("video_minutes") == 22.5, str(saved.get("video_minutes")))
check("thong bao noi luon phien dai bao nhieu", "Video đối thủ ~22 phút" in status.cget("text") and "mỗi phiên khoảng" in status.cget("text"),
      status.cget("text"))
lst = [x for x in walk(nd) if isinstance(x, tk.Listbox)][0]
buttons["+ Niche mới"].invoke()
check("niche moi -> o trong lai", ent_len.get() == "")
lst.selection_set(0)
lst.event_generate("<<ListboxSelect>>")
root.update()
check("chon lai niche -> nap lai 22.5", ent_len.get() == "22.5")
ent_len.delete(0, "end")
buttons["Lưu niche"].invoke()
check("xoa trang o -> ve 0 (bot tu do)", app_config.load_config()["niches"][0].get("video_minutes") == 0)
nd.destroy()
root.update()

CAP = {}


class FakeWorkflow:
    def __init__(self, **kw):
        self.session_deadline_s = 0
        self.niche = {}
        self.actions_done = 0
        CAP["wf"] = self

    def run_random_session(self, total_actions=5):
        pass


class FakeAPI:
    last_error = ""

    def open_profile(self, pid):
        return "ws://fake"

    def close_profile(self, pid):
        return True


class FakeBrowser:
    def __init__(self):
        self.contexts = [FakeContext()]


class FakeController:
    def __init__(self, ws):
        self.browser = FakeBrowser()

    def connect(self):
        return True

    def close(self):
        pass


out = []
_o = (ui.WarmupWorkflow, ui.BrowserController, ui.adjust_window_bounds, ui.time.sleep, sys.stdout)
ui.WarmupWorkflow, ui.BrowserController = FakeWorkflow, FakeController
ui.adjust_window_bounds = lambda *a, **k: None
ui.time.sleep = lambda *_a, **_k: None


class _Cap:
    def write(self, s):
        out.append(s)

    def flush(self):
        pass


THEMES = [{"google_query": "g", "youtube_query": "y"}]
NICHE30 = dict(RAW, video_minutes=30)
sys.stdout = _Cap()
try:
    ui.run_single_profile(FakeAPI(), "pid-1", "Kenh 1", THEMES, 0, 1920, 1080, False, False, "none",
                          "channel", 0, 0, "", None, "en", niche=NICHE30)
    a = (CAP["wf"].session_deadline_s, getattr(CAP["wf"], "channel_max_s", 0), "".join(out))
    out.clear()
    ui.run_single_profile(FakeAPI(), "pid-2", "Kenh 2", THEMES, 0, 1920, 1080, False, False, "none",
                          "channel", 0, 90 * 60, "", None, "en", niche=NICHE30)
    b = (CAP["wf"].session_deadline_s, getattr(CAP["wf"], "channel_max_s", 0), "".join(out))
    out.clear()
    ui.run_single_profile(FakeAPI(), "pid-3", "Kenh 3", THEMES, 0, 1920, 1080, False, False, "none",
                          "channel", 0, 30 * 60, "", None, "en", niche=NICHE30)
    c = (CAP["wf"].session_deadline_s, getattr(CAP["wf"], "channel_max_s", 0), "".join(out))
    out.clear()
    ui.run_single_profile(FakeAPI(), "pid-4", "Kenh 4", THEMES, 0, 1920, 1080, False, False, "none",
                          "channel", 0, 0, "", None, "en", niche=RAW)
    d = "".join(out)
    out.clear()
    ui.run_single_profile(FakeAPI(), "pid-5", "Acc thuong", THEMES, 0, 1920, 1080, False, False, "none",
                          "clean", 0, 90 * 60, "", None, "en")
    e = (CAP["wf"].session_deadline_s, getattr(CAP["wf"], "channel_max_s", 0))
finally:
    sys.stdout = _o[4]
    ui.WarmupWorkflow, ui.BrowserController, ui.adjust_window_bounds, ui.time.sleep = _o[:4]
check("khong han muc: de bot tu tinh, log bao phien theo video 30 phut", a[0] == 0 and a[1] == 0
      and "tính theo video đối thủ dài ~30 phút" in a[2], a[2][-300:])
check("han muc con 90 phut: khong ghim tran, dua 90 phut lam tran cung", b[0] == 0 and b[1] == 90 * 60, str(b[:2]))
check("han muc con 30 phut: siet tran 30 phut + canh bao thieu so voi video doi thu", c[0] == 30 * 60
      and "video đối thủ dài ~30 phút cần khoảng" in c[2], c[2][-400:])
check("niche chua biet do dai: log noi bot tu do", "tự đo độ dài video đối thủ" in d, d[-300:])
check("pha khac khong bi anh huong", e == (0, 0), str(e))
root.destroy()

for p, h in BEFORE.items():
    check(f"file that khong doi: {os.path.basename(p)}", _hash(p) == h)

print(f"\nPASS: {PASS}  FAIL: {FAIL}")
print("SMOKE v1.9.5: ALL PASS" if FAIL == 0 else "SMOKE v1.9.5: CO LOI")
sys.exit(0 if FAIL == 0 else 1)
