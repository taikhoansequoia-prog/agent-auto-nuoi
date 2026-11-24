# -*- coding: utf-8 -*-
"""
Smoke test v1.9.3 — CHẾ ĐỘ 4 "NGÂM KÊNH THEO NICHE" (workflow/channel_mode.py).

Chạy:  python test_v193.py
Cô lập: GPM_BOT_DATA_DIR -> temp dir (KHÔNG đụng data thật; hash DB + app_config thật trước == sau).

Phủ:
  [1] Hàm thuần: parse_count / parse_age_hours / parse_duration / views_per_hour (vi + en)
  [2] Niche: normalize_niche, channel_key, niche_score (kênh đối thủ, token, từ loại trừ), pick_by_vph,
      parse_ai_numbers, pick_niche (tên riêng > nhóm > mọi nhóm)
  [3] WarmupWorkflow: nhận phase 'channel', run_random_session chuyển sang run_channel_session,
      3 pha cũ KHÔNG bị ảnh hưởng; thứ tự từ khóa; kế hoạch tương tác (thưa + trần ngày/tuần + chưa login)
  [4] Phiên giả lập đủ 5 bước (stub mọi bước chạm trình duyệt): thứ tự bước, video 1 = deep, còn lại = mid,
      không bao giờ có hành động 'comment'
  [5] DB count_activity (hôm nay / 7 ngày / bỏ row lỗi) + VALID_PHASES
  [6] UI: nhãn chế độ 4, PHASE_DETAILS, STAGE_PHASE_SHORT, hộp Niche (thêm/sửa/xóa + ghi config),
      resolve_profile_niches, run_single_profile gán niche + trần phiên 45-60 phút
  [7] Tĩnh: không có code gõ bình luận; selector chốt từ diag có mặt
"""
import hashlib
import os
import sys
import tempfile
import time
import datetime as dt
import random
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

TMP = tempfile.mkdtemp(prefix="gpm_v193_")
DATA_DIR = os.path.join(TMP, "data")
os.makedirs(DATA_DIR, exist_ok=True)
REAL_DB = os.path.join(REPO, "data", "agent_logs.db")
REAL_CFG = os.path.join(REPO, "data", "app_config.json")


def _hash(path):
    try:
        return hashlib.sha256(open(path, "rb").read()).hexdigest()
    except Exception:
        return None


REAL_DB_BEFORE, REAL_CFG_BEFORE = _hash(REAL_DB), _hash(REAL_CFG)
os.environ["GPM_BOT_DATA_DIR"] = DATA_DIR

from src.database.db_handler import DatabaseHandler  # noqa: E402
from src.database import db_handler as dbm  # noqa: E402
from src.workflow import channel_mode as cm  # noqa: E402
from src.workflow.warmup import WarmupWorkflow  # noqa: E402
from src import ui_main as ui  # noqa: E402
from src import app_config  # noqa: E402

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


# ---------------------------------------------------------------- [1]
print("\n[1] Ham thuan: doc so lieu tren trang")
for txt, want in [("34 N", 34000), ("2,9 Tr", 2900000), ("12 Tr", 12000000), ("820 N", 820000),
                  ("7,9 N", 7900), ("1.2M views", 1200000), ("100K views", 100000), ("1,234 views", 1234),
                  ("1.234 lượt xem", 1234), ("34 N lượt xem", 34000), ("3B views", 3000000000),
                  ("987 views", 987), ("5 watching", 5), ("1 T", 1000000000)]:
    check(f"parse_count({txt!r}) = {want}", cm.parse_count(txt) == want, f"-> {cm.parse_count(txt)}")
check("parse_count rong -> None", cm.parse_count("") is None and cm.parse_count("No views") is None)
for txt, want in [("2 days ago", 48), ("19 giờ trước", 19), ("5 ngày trước", 120), ("1 năm trước", 8760),
                  ("3 weeks ago", 504), ("Streamed 2 hours ago", 2), ("7 năm trước", 61320),
                  ("2 tháng trước", 1460), ("1 month ago", 730)]:
    check(f"parse_age_hours({txt!r}) = {want}", abs((cm.parse_age_hours(txt) or -1) - want) < 0.01)
check("parse_age_hours '30 minutes ago' = 0.5", abs(cm.parse_age_hours("30 minutes ago") - 0.5) < 1e-6)
# Giao dien English viet tat (do that 23/11: meta = ["34K", "2d ago"]) -> ban dau doc ra None = "chua ro VPH"
for txt, want in [("2d ago", 48), ("20h ago", 20), ("3w ago", 504), ("2mo ago", 1460), ("1y ago", 8760),
                  ("1 hr ago", 1), ("2 yrs ago", 17520), ("3 mos ago", 2190)]:
    check(f"parse_age_hours viet tat {txt!r} = {want}", abs((cm.parse_age_hours(txt) or -1) - want) < 0.01)
check("parse_age_hours '5m ago' = 5 phut", abs(cm.parse_age_hours("5m ago") - 5 / 60.0) < 1e-6)
for txt in ("34K", "5.1K", "1.2M", "12M views", "3B", "1.2M views", "2,9 Tr", "820 N", "5 watching", "12 Tr"):
    check(f"luot xem {txt!r} KHONG bi doc nham thanh tuoi video", cm.parse_age_hours(txt) is None,
          str(cm.parse_age_hours(txt)))
check("parse_count viet tat 34K / 5.1K", cm.parse_count("34K") == 34000 and cm.parse_count("5.1K") == 5100)
check("parse_age_hours khong doc duoc -> None", cm.parse_age_hours("LIVE") is None and cm.parse_age_hours("") is None)
check("parse_duration 18:41 / 1:00:45 / rong", (cm.parse_duration("18:41"), cm.parse_duration("1:00:45"),
                                               cm.parse_duration(""), cm.parse_duration("LIVE")) == (1121, 3645, 0, 0))
check("VPH 100K views / 2 days = 2083", round(cm.views_per_hour(100000, 48)) == 2083)
check("VPH video < 1 gio tinh nhu 1 gio", cm.views_per_hour(5000, 0.25) == 5000.0)
check("VPH thieu so lieu = 0", cm.views_per_hour(None, 5) == 0.0 and cm.views_per_hour(100, None) == 0.0)

# ---------------------------------------------------------------- [2]
print("\n[2] Niche: chuan hoa + cham diem")
RAW = {
    "name": "Deep sea exploration",
    "description": "Ocean trench documentaries for a US audience",
    "keywords": "how deep is the mariana trench\nmariana trench documentary\ndeep sea creatures explained\n"
                "what lives at the bottom of the ocean\nMariana Trench Documentary",
    "channels": ["https://www.youtube.com/@BBCNews/videos", "@NatGeo", "Ocean Discover",
                 "https://www.youtube.com/channel/UCabc123XYZ"],
    "negative": ["kids", "minecraft"],
    "groups": ["Kenh A"],
}
N = cm.normalize_niche(RAW)
check("keywords tach dong + bo trung (khong phan biet hoa thuong)", len(N["keywords"]) == 4, str(N["keywords"]))
check("channel_keys tu link/handle/ten", N["channel_keys"] == {"bbcnews", "natgeo", "oceandiscover", "ucabc123xyz"},
      str(N["channel_keys"]))
check("token loi (>=2 tu khoa hoac trong ten/mo ta) = 2 diem",
      N["tokens"].get("mariana") == 2 and N["tokens"].get("trench") == 2 and N["tokens"].get("ocean") == 2
      and N["tokens"].get("sea") == 2)
check("token thuong = 1 diem, stopword bi loai", N["tokens"].get("creatures") == 1 and "the" not in N["tokens"]
      and "how" not in N["tokens"] and "what" not in N["tokens"])
check("sync_locale mac dinh True", N["sync_locale"] is True)
check("niche rong -> khong vo", cm.normalize_niche(None)["keywords"] == [] and cm.normalize_niche({})["tokens"] == {})
check("channel_key link co duoi /videos", cm.channel_key("https://www.youtube.com/@BBCNews/videos") == "bbcnews")
check("channel_key ten hien thi == handle", cm.channel_key("BBC News") == cm.channel_key("/@BBCNews"))

sc = lambda t, c="", h="": cm.niche_score(N, t, c, h)[0]
check("dung niche: tieu de khop token loi", sc("What's Waiting At The Bottom Of The Mariana Trench") >= cm.NICHE_SCORE_MIN)
check("dung niche: chua nguyen tu khoa duoc cong them", sc("Mariana Trench Documentary 4K") > sc("Mariana Trench 4K"))
check("lac niche: tieu de khong lien quan", sc("TỔNG HỢP PVZ VẼ VỜI") < cm.NICHE_SCORE_MIN and
      sc("Top 10 goals of the season") < cm.NICHE_SCORE_MIN)
check("kenh doi thu (theo href) luon dung niche", sc("Breaking: election results", "BBC News", "/@BBCNews") >= 6)
check("kenh doi thu (theo ten hien thi)", sc("Something unrelated", "Ocean Discover", "") >= 6)
check("kenh la KHONG duoc cong diem kenh", sc("Something unrelated", "Random Channel", "/@random") == 0)
check("tu loai tru keo diem xuong duoi nguong",
      sc("Mariana Trench for Kids") < cm.NICHE_SCORE_MIN, str(sc("Mariana Trench for Kids")))
check("so nhieu van khop (trenches/oceans)", sc("Ocean Trenches: The Abyssal Worlds") >= cm.NICHE_SCORE_MIN)
check("khong khop chuoi con (seaside != sea)", sc("Seaside holiday vlog") == 0, str(sc("Seaside holiday vlog")))
check("niche_score niche rong = 0", cm.niche_score({}, "Mariana Trench")[0] == 0)

rng = random.Random(7)
cands = [{"t": "a", "vph": 10}, {"t": "b", "vph": 5000}, {"t": "c", "vph": 300}, {"t": "d", "vph": 0},
         {"t": "e", "vph": 1}, {"t": "f", "vph": 2}]
picks = [cm.pick_by_vph(cands, k=3, rng=rng)["t"] for _ in range(400)]
check("pick_by_vph chi lay trong top-k theo VPH", set(picks) <= {"a", "b", "c"}, str(set(picks)))
check("pick_by_vph uu tien VPH cao nhat", picks.count("b") > picks.count("c") > picks.count("a"))
check("pick_by_vph rong -> None", cm.pick_by_vph([]) is None)
check("parse_ai_numbers '2, 5' -> [1,4]", cm.parse_ai_numbers("2, 5", 6) == [1, 4])
check("parse_ai_numbers bo so ngoai khoang + trung", cm.parse_ai_numbers("Videos: 3, 3, 9 and 1", 5) == [2, 0])
check("parse_ai_numbers 'none' -> []", cm.parse_ai_numbers("None", 5) == [] and cm.parse_ai_numbers("none.", 5) == [])
check("parse_ai_numbers vo nghia -> None", cm.parse_ai_numbers("I cannot tell", 5) is None and
      cm.parse_ai_numbers("", 5) is None)

NA = {"name": "A", "keywords": ["x"], "groups": ["Kenh A"]}
NB = {"name": "B", "keywords": ["y"], "groups": []}
NC = {"name": "C", "keywords": ["z"], "groups": ["Kenh C", "Kenh D"]}
check("pick_niche: ten rieng cua acc thang nhom", cm.pick_niche([NA, NB, NC], "Kenh A", "c")["name"] == "C")
check("pick_niche: theo nhom GPM (khong phan biet hoa thuong)", cm.pick_niche([NA, NB, NC], "kenh d")["name"] == "C")
check("pick_niche: nhom la -> niche moi nhom", cm.pick_niche([NA, NB, NC], "Nhom khac")["name"] == "B")
check("pick_niche: niche co ghi nhom KHONG ap cho nhom khac", cm.pick_niche([NA, NC], "Nhom khac") == {})
check("pick_niche: danh sach rong / thieu ten", cm.pick_niche([], "x") == {} and cm.pick_niche([{"keywords": ["a"]}], "") == {})


# ---------------------------------------------------------------- [3]
print("\n[3] WarmupWorkflow nhan che do 'channel'")


class FakeContext:
    def __init__(self):
        self.pages = []

    def on(self, *_a, **_k):
        pass

    def new_page(self):
        pg = FakePage()
        self.pages.append(pg)
        return pg


class FakePage:
    def __init__(self):
        self.url = "about:blank"
        self.closed = False

    def close(self):
        self.closed = True

    def is_closed(self):
        return False

    def title(self):
        return "Fake video - YouTube"


class FakeDB:
    def __init__(self, counts=None, can_sub=True, last=None):
        self.counts, self.can_sub, self.last, self.logged = counts or {}, can_sub, last or {}, []

    def count_activity(self, pid, action, days=1):
        return self.counts.get((action, days), 0)

    def can_subscribe_today(self, pid):
        return self.can_sub

    def get_keyword_last_used(self, pid, kws=None):
        return self.last

    def log_keyword_used(self, pid, kw):
        return True

    def log_activity(self, pid, action, platform="", url="", title="", status="ok", duration_s=None, error=None):
        self.logged.append((action, platform, title, status))
        return True


wf = WarmupWorkflow(context=FakeContext(), phase="channel", profile_id="P-CH")
check("phase 'channel' duoc giu nguyen", wf.phase == "channel")
check("phase la -> 'clean' nhu cu", WarmupWorkflow(context=FakeContext(), phase="xyz").phase == "clean")
check("3 pha cu van hop le", all(WarmupWorkflow(context=FakeContext(), phase=p).phase == p
                                 for p in ("clean", "mail", "youtube")))
check("niche mac dinh rong", wf.niche == {})
check("WarmupWorkflow co du ham che do 4", all(hasattr(wf, n) for n in (
    "run_channel_session", "_ch_sync_locale", "_ch_cross_signal", "_ch_search", "_ch_watch", "_ch_home_training")))

called = {}
wf.run_channel_session = lambda: called.setdefault("ch", True)
wf.run_random_session(total_actions=3)
check("run_random_session -> run_channel_session khi phase=channel", called.get("ch") is True)
check("phase=channel KHONG mo tab cua phien ngau nhien", wf.context.pages == [])

wf2 = WarmupWorkflow(context=FakeContext(), phase="channel", profile_id="P-CH",
                     db_handler=FakeDB(last={"kw b": "2026-11-20T10:00:00", "kw c": "2026-11-22T10:00:00"}))
order = wf2._ch_keyword_order(cm.normalize_niche({"name": "n", "keywords": ["kw a", "kw b", "kw c", "kw d"]}))
check("tu khoa chua dung len truoc, dung gan nhat xuong cuoi",
      set(order[:2]) == {"kw a", "kw d"} and order[2:] == ["kw b", "kw c"], str(order))
wf3 = WarmupWorkflow(context=FakeContext(), phase="channel",
                     session_theme={"google_query": "g theme", "youtube_query": "y theme"})
check("chua co niche -> tam dung tu khoa cua phien",
      set(wf3._ch_keyword_order(cm.normalize_niche({}))) == {"g theme", "y theme"})

print("    -- ke hoach tuong tac")
wfe = WarmupWorkflow(context=FakeContext(), phase="channel", profile_id="P-E", db_handler=FakeDB())
plan = wfe._ch_roll_engagement(False)
check("chua dang nhap -> khong like/sub gi", plan == {"like_video": False, "like_comment": False, "subscribe": False})
random.seed(11)
rolls = [wfe._ch_roll_engagement(True) for _ in range(3000)]
lv = sum(r["like_video"] for r in rolls) / 3000
lc = sum(r["like_comment"] for r in rolls) / 3000
sb = sum(r["subscribe"] for r in rolls) / 3000
check(f"like video thua ~28% so phien (do duoc {lv:.1%})", 0.24 < lv < 0.32)
check(f"like binh luan rat thua ~12% (do duoc {lc:.1%})", 0.09 < lc < 0.15)
check(f"dang ky rat thua ~12% (do duoc {sb:.1%})", 0.09 < sb < 0.15)
check("khong co khoa 'comment' trong ke hoach", all("comment" not in k or k == "like_comment" for k in rolls[0]))
wfe.db = FakeDB(counts={("like_video", 1): 1, ("like_comment", 1): 1, ("subscribe", 7): 2})
capped = [wfe._ch_roll_engagement(True) for _ in range(400)]
check("da cham tran ngay/tuan -> khong like/sub nua", not any(r["like_video"] or r["like_comment"] or r["subscribe"]
                                                               for r in capped))
wfe.db = FakeDB(can_sub=False)
check("hom nay da sub (subscriptions) -> khong sub", not any(wfe._ch_roll_engagement(True)["subscribe"] for _ in range(400)))

# ---------------------------------------------------------------- [4]
print("\n[4] Phien gia lap du 5 buoc")


def make_session(n_keywords=6, landed=True, deadline=0):
    db = FakeDB()
    w = WarmupWorkflow(context=FakeContext(), phase="channel", profile_id="P-S", db_handler=db)
    w.niche = dict(RAW)
    w.session_deadline_s = deadline
    ev = []
    w.enable_virtual_cursor = lambda page: None
    w._ch_goto = lambda page, url: ev.append(("goto", url))
    w._pump_wait = lambda page, s: None
    w._close_popups = lambda page: None
    w._ch_rest = lambda page, lo, hi: None
    w._browser_gone = lambda page: False
    w._ch_sync_locale = lambda page: (ev.append(("sync",)) or {"GL": "US", "HL": "en", "LOGGED_IN": True})
    w._ch_cross_signal = lambda page, q: (ev.append(("google", q)) or landed)
    w._ch_search = lambda page, kw, use_filter: (ev.append(("search", kw, use_filter)) or use_filter)

    def _rows(page, niche):
        k = sum(1 for e in ev if e[0] == "search")
        return [{"idx": i, "title": f"Mariana Trench documentary part {k}-{i}", "chan": "Ocean Discover",
                 "views": 50000, "age_h": 30.0, "vph": 1000.0 + i, "dur_s": 900, "score": 8, "why": "t"}
                for i in range(6)]
    w._ch_read_results = _rows
    w._ch_open_search_result = lambda page, row: (ev.append(("open", row["title"])) or True)
    w._ch_watch = lambda page, role, in_niche=True: (ev.append(("watch", role, in_niche)) or
                                                     {"title": f"w{len(ev)}", "watched_s": 1, "ratio": 0.8})
    w._ch_shorts = lambda page: (ev.append(("shorts",)) or 2)
    w._ch_home_training = lambda page, niche, seen: (ev.append(("home", len(seen))) or 1)
    return w, ev, db


random.seed(3)
w, ev, db = make_session()
w.run_channel_session()
kinds = [e[0] for e in ev]
check("buoc 1: vao YouTube -> dong bo vung/ngon ngu -> Google", kinds[:3] == ["goto", "sync", "google"], str(kinds[:4]))
check("video den tu Google duoc xem kieu 'light'", ("watch", "light", True) in ev and
      kinds.index("watch") == 3)
roles = [e[1] for e in ev if e[0] == "watch"][1:]
check(f"3-5 video dai (do duoc {len(roles)})", 3 <= len(roles) <= 5)
check("video dai dau tien = deep, cac video sau = mid", roles[0] == "deep" and set(roles[1:]) == {"mid"}, str(roles))
searches = [e for e in ev if e[0] == "search"]
check("lan tim dau tien LUON co bo loc (SOP)", searches[0][2] is True)
check("moi lan tim dung tu khoa khac nhau cua niche",
      len({e[1] for e in searches} | {e[1] for e in ev if e[0] == "google"}) >= min(4, len(searches) + 1))
check("trang chu chay SAU cac video dai va la buoc cuoi", kinds[-1] == "home" and kinds.count("home") == 1)
check("dong tab cuoi phien", w.context.pages[0].closed is True)
check("ghi activity dong bo vung/ngon ngu", any(a[0] == "channel_sync_locale" for a in db.logged))
check("actions_done > 0 (bao cao chu trinh)", isinstance(w.actions_done, int) and w.actions_done >= 5)
# v1.9.5: tran phien tinh theo do dai video (ket qua gia dai 15 phut) -> 45-150 phut, khong con co dinh 45-60
check("tran phien tinh theo do dai video nam trong 45-150 phut", 45 * 60 <= w.session_deadline_s <= 150 * 60, str(w.session_deadline_s))
check("khong co hanh dong nao ten 'comment' (chi like_comment)", not any(a[0] == "comment" for a in db.logged))

w, ev, db = make_session(landed=False)
w.run_channel_session()
check("Google khong dap YouTube -> khong xem 'light', van di tiep buoc 2",
      not any(e[0] == "watch" and e[1] == "light" for e in ev) and any(e[0] == "search" for e in ev))

w, ev, db = make_session(deadline=600)       # caller ep tran 10 phut
w.run_channel_session()
check("tran phien do caller dat duoc giu nguyen", w.session_deadline_s == 600)
check("con it gio -> bo video dai, van chay trang chu",
      not any(e[0] == "watch" and e[1] in ("deep", "mid") for e in ev) and any(e[0] == "home" for e in ev))

w, ev, db = make_session()
w._should_stop_cb = lambda: True
w.run_channel_session()
check("nguoi dung bam Dung -> khong xem video nao, van dong tab",
      not any(e[0] == "watch" for e in ev) and w.context.pages[0].closed is True)

w, ev, db = make_session()
w.niche = {}
w.session_theme = {"google_query": "", "youtube_query": ""}
w.keyword_cluster = []
w.run_channel_session()
check("khong co tu khoa nao -> ket thuc phien em, khong vao YouTube", ev == [] and w.context.pages[0].closed)

w, ev, db = make_session()
w._browser_gone = lambda page: True
try:
    w.run_channel_session()
    raised = False
except RuntimeError:
    raised = True
check("trinh duyet bi dong giua phien -> nem loi (chu trinh ghi 'error', tra slot)", raised)
check("...va van dong tab trong finally", w.context.pages[0].closed is True)

print("    -- chon video")
wc = WarmupWorkflow(context=FakeContext(), phase="channel")
for meta, want_v, want_a in ((["34K", "2d ago"], 34000, 48.0), (["34 N", "2 ngày trước"], 34000, 48.0),
                             (["1.2M views", "3 weeks ago"], 1200000, 504.0), (["5,1 N", "20 giờ trước"], 5100, 20.0)):
    wc._ch_js = lambda page, code, arg=None, _m=meta: [{"idx": 0, "title": "Mariana Trench", "href": "/watch?v=abc",
                                                        "chan": "X", "chanHref": "/@x", "meta": _m, "dur": "18:41", "h": 120}]
    row = wc._ch_read_results(None, N)[0]
    check(f"doc ket qua {meta} -> luot xem {want_v}, tuoi {want_a}h, co VPH",
          row["views"] == want_v and row["age_h"] == want_a and row["vph"] > 0 and row["dur_s"] == 1121, str(row))
del wc._ch_js
rows = [
    {"idx": 0, "title": "lac de", "vph": 9999.0, "dur_s": 600, "score": 0},
    {"idx": 1, "title": "dung niche ngan", "vph": 50.0, "dur_s": 200, "score": 5},
    {"idx": 2, "title": "dung niche vua", "vph": 800.0, "dur_s": 900, "score": 5},
    {"idx": 3, "title": "dung niche rat dai", "vph": 900.0, "dur_s": 9000, "score": 5},
    {"idx": 4, "title": "shorts 40s", "vph": 5000.0, "dur_s": 40, "score": 5},
]
got = {wc._ch_choose_result(rows, True, set())[0]["title"] for _ in range(60)}
check("video xem sau: dung niche + dai 6-25 phut", got == {"dung niche vua"}, str(got))
got = {wc._ch_choose_result(rows, False, set())[0]["title"] for _ in range(200)}
check("khong bao gio chon video lac de khi co video dung niche", "lac de" not in got and "shorts 40s" not in got, str(got))
check("bo video da xem", wc._ch_choose_result(rows, True, {"dung niche vua"})[0]["title"] != "dung niche vua")
r, note = wc._ch_choose_result([rows[0]], False, set())
check("khong cham duoc niche -> lay theo thu hang + ghi ro ly do", r["title"] == "lac de" and "chưa chấm" in note)
check("het ket qua -> None", wc._ch_choose_result([], True, set())[0] is None)

print("    -- cham the trang chu (co / khong AI)")


class Brain:
    def __init__(self, reply):
        self.reply, self.prompts = reply, []

    def ask_text(self, prompt):
        self.prompts.append(prompt)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


tiles = lambda: [{"vid": "a", "title": "Mariana Trench deep dive", "chan": "X", "chanHref": "/@x"},
                 {"vid": "b", "title": "Funny cats compilation", "chan": "Y", "chanHref": "/@y"},
                 {"vid": "c", "title": "Abyssal zone explained", "chan": "Z", "chanHref": "/@z"},
                 {"vid": "d", "title": "Weekly politics roundup", "chan": "BBC News", "chanHref": "/@BBCNews"}]
wc.brain = None
good = [t["vid"] for t in wc._ch_score_tiles(N, tiles())]
check("khong AI: lay theo tu khoa + kenh doi thu", set(good) == {"a", "d"}, str(good))
wc.brain = Brain("1, 3")
good = [t["vid"] for t in wc._ch_score_tiles(N, tiles())]
check("co AI: AI them video dung niche ma tu khoa bo sot (c)", "c" in good and "a" in good, str(good))
check("co AI: kenh doi thu khong bi AI loai (d)", "d" in good and "b" not in good, str(good))
check("prompt AI co ten niche + danh sach danh so", "Deep sea exploration" in wc.brain.prompts[0] and
      "2. Funny cats compilation" in wc.brain.prompts[0])
wc.brain = Brain("none")
good = [t["vid"] for t in wc._ch_score_tiles(N, tiles())]
check("AI noi 'none' -> chi con kenh doi thu", good == ["d"], str(good))
wc.brain = Brain(RuntimeError("timeout"))
good = [t["vid"] for t in wc._ch_score_tiles(N, tiles())]
check("AI loi -> tu dung bo cham tai cho", set(good) == {"a", "d"}, str(good))

# ---------------------------------------------------------------- [5]
print("\n[5] DB count_activity")
check("VALID_PHASES co 'channel'", dbm.VALID_PHASES == ("clean", "mail", "youtube", "channel"))
check("giai doan sheet KHONG tu suy ra 'channel'", "channel" not in set(dbm.STAGE_SUGGESTED_PHASE.values()))
db = DatabaseHandler()
PID = "P-COUNT"
db.log_activity(PID, "like_video", "YouTube", "u", "t1")
db.log_activity(PID, "like_video", "YouTube", "u", "t2", status="error", error="x")
db.log_activity(PID, "subscribe", "YouTube", "u", "t3")
import sqlite3  # noqa: E402
conn = sqlite3.connect(db.db_path)
old3 = (dt.datetime.now() - dt.timedelta(days=3)).isoformat(timespec="seconds")
old9 = (dt.datetime.now() - dt.timedelta(days=9)).isoformat(timespec="seconds")
for ts in (old3, old9):
    conn.execute("INSERT INTO activity_history (profile_id, action, platform, url, title, created_at, status) "
                 "VALUES (?, 'subscribe', 'YouTube', 'u', 'old', ?, 'ok')", (PID, ts))
conn.commit()
conn.close()
check("hom nay: 1 like (bo row loi)", db.count_activity(PID, "like_video", 1) == 1)
check("hom nay: 1 sub", db.count_activity(PID, "subscribe", 1) == 1)
check("7 ngay: 2 sub (bo row 9 ngay truoc)", db.count_activity(PID, "subscribe", 7) == 2)
check("30 ngay: 3 sub", db.count_activity(PID, "subscribe", 30) == 3)
check("profile/hanh dong la -> 0", db.count_activity("nobody", "subscribe", 7) == 0 and db.count_activity(PID, "", 7) == 0)
check("pin 'channel' cho 1 acc duoc DB nhan", db.set_profile_stage_meta(PID, phase_override="channel") is True and
      (db.get_profile_stage_rows().get(PID) or {}).get("phase_override") == "channel")

# ---------------------------------------------------------------- [6]
print("\n[6] Giao dien")
check("4 nhan che do, nhan 4 = Ngam kenh", len(ui.PHASE_LABELS) == 4 and ui.PHASE_LABELS[3].startswith("4 - Ngâm kênh"))
check("PHASE_MAP nhan 4 -> 'channel'", ui.PHASE_MAP[ui.PHASE_LABELS[3]] == "channel" and
      ui.PHASE_LABEL_BY_KEY["channel"] == ui.PHASE_LABELS[3])
check("3 nhan cu khong doi", [ui.PHASE_MAP[l] for l in ui.PHASE_LABELS[:3]] == ["clean", "mail", "youtube"])
check("PHASE_DETAILS co 'channel' du 5 buoc", len(ui.PHASE_DETAILS["channel"]["actions"]) == 7 and
      "KHÔNG BAO GIỜ viết bình luận" in ui.PHASE_DETAILS["channel"]["notes"])
check("app_config.DEFAULTS co 'niches' = []", app_config.DEFAULTS.get("niches") == [])

root = tk.Tk()
root.geometry("1200x820+0+0")
app = ui.AutomationApp(root)
root.update()
check("STAGE_PHASE_SHORT co '4 · Ngâm kênh'", app.STAGE_PHASE_SHORT.get("channel") == "4 · Ngâm kênh")
check("combobox che do co 4 lua chon", len(app.cbo_phase.cget("values")) == 4)
check("co nut 'Niche ngâm kênh' tren thanh cong cu", str(app.btn_niche.cget("text")) == "Niche ngâm kênh")
app.var_phase_label.set(ui.PHASE_LABELS[3])
app._on_phase_changed()
check("hint che do 4 noi ro 45-60 phut + khong binh luan",
      "45-60 phút" in app.lbl_phase_hint.cget("text") and "không viết bình luận" in app.lbl_phase_hint.cget("text"))
app.save_current_config()
check("config luu phase = 'channel'", app_config.load_config().get("phase") == "channel")


def toplevels():
    return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]


def walk(w):
    yield w
    for c in w.winfo_children():
        yield from walk(c)


app.show_phase_details()
root.update()
dlg = [w for w in toplevels() if "chế độ ngâm" in w.title()][0]
nb = [w for w in walk(dlg) if isinstance(w, ttk.Notebook)][0]
check("hop CHI TIET co 4 tab, mo san tab che do 4", len(nb.tabs()) == 4 and nb.index(nb.select()) == 3)
dlg.destroy()

app.profile_rows[:] = [{"id": "pid-a", "name": "Kenh A1", "firefox": False, "var": tk.BooleanVar(value=True),
                        "frame": None, "group": "Kenh A"},
                       {"id": "pid-b", "name": "Kenh B1", "firefox": False, "var": tk.BooleanVar(value=True),
                        "frame": None, "group": "Nhom khac"}]
app.cfg["niches"] = []
app.open_niche_manager()
root.update()
nd = app._niche_dialog
check("hop Niche mo duoc", nd is not None and nd.winfo_exists())
app.open_niche_manager()
check("bam lan 2 khong mo them cua so", len([w for w in toplevels() if w.title().startswith("Niche ngâm kênh")]) == 1)
entries = [w for w in walk(nd) if isinstance(w, ttk.Entry)]
texts = [w for w in walk(nd) if isinstance(w, tk.Text)]
buttons = {str(b.cget("text")): b for b in walk(nd) if isinstance(b, ttk.Button)}
lst = [w for w in walk(nd) if isinstance(w, tk.Listbox)][0]
status = [w for w in walk(nd) if isinstance(w, tk.Label)][-1]
check("form co 4 o nhap + 2 o nhieu dong + 4 nut", len(entries) == 7 and len(texts) == 2 and
      {"+ Niche mới", "Xóa", "Lưu niche", "Đóng"} <= set(buttons))


def set_entry(en, text):
    en.delete(0, "end")
    en.insert(0, text)


buttons["Lưu niche"].invoke()
check("thieu ten -> khong luu", app.cfg.get("niches") == [] and "Thiếu tên" in status.cget("text"))
set_entry(entries[0], "Deep sea")
buttons["Lưu niche"].invoke()
check("thieu tu khoa -> khong luu", app.cfg.get("niches") == [] and "ít nhất 1 từ khóa" in status.cget("text"))
set_entry(entries[1], "Ocean trench docs")
texts[0].insert("1.0", "mariana trench documentary\n\n  deep sea creatures  \nmariana trench documentary\n")
texts[1].insert("1.0", "https://www.youtube.com/@NatGeo\n@BBCNews\n")
set_entry(entries[2], "kids; minecraft")
set_entry(entries[3], "Kenh A")
buttons["Lưu niche"].invoke()
root.update()
saved = app_config.load_config().get("niches")
check("luu niche vao app_config.json", len(saved) == 1 and saved[0]["name"] == "Deep sea", str(saved))
check("tu khoa: bo dong trong + trung + khoang trang", saved[0]["keywords"] == ["mariana trench documentary", "deep sea creatures"])
check("kenh / tu loai tru / nhom duoc tach dung", saved[0]["channels"] == ["https://www.youtube.com/@NatGeo", "@BBCNews"]
      and saved[0]["negative"] == ["kids", "minecraft"] and saved[0]["groups"] == ["Kenh A"] and saved[0]["sync_locale"] is True)
check("canh bao it tu khoa", "mới có 2 từ khóa" in status.cget("text"))
check("danh sach hien 1 niche", lst.size() == 1 and "Deep sea" in lst.get(0))

buttons["+ Niche mới"].invoke()
set_entry(entries[0], "deep SEA")
texts[0].insert("1.0", "abc")
buttons["Lưu niche"].invoke()
check("trung ten (khong phan biet hoa thuong) -> tu choi", len(app.cfg["niches"]) == 1 and "Đã có niche" in status.cget("text"))
set_entry(entries[0], "Cooking")
buttons["Lưu niche"].invoke()
check("them niche thu 2 (moi nhom)", [n["name"] for n in app_config.load_config()["niches"]] == ["Deep sea", "Cooking"])

lst.selection_clear(0, "end")
lst.selection_set(0)
lst.event_generate("<<ListboxSelect>>")
root.update()
check("chon niche -> form nap lai du lieu", entries[0].get() == "Deep sea" and
      texts[0].get("1.0", "end").strip().splitlines() == ["mariana trench documentary", "deep sea creatures"])
set_entry(entries[1], "Mo ta moi")
buttons["Lưu niche"].invoke()
check("sua niche giu nguyen vi tri, khong nhan doi",
      [n["name"] for n in app.cfg["niches"]] == ["Deep sea", "Cooking"] and app.cfg["niches"][0]["description"] == "Mo ta moi")

m = app.resolve_profile_niches(["pid-a", "pid-b"])
check("acc nhom 'Kenh A' nhan niche Deep sea, acc nhom khac nhan niche moi nhom",
      m["pid-a"]["name"] == "Deep sea" and m["pid-b"]["name"] == "Cooking")
DatabaseHandler().set_profile_stage_meta("pid-b", niche="deep sea")
check("ghi ten niche rieng cho acc -> thang nhom", app.resolve_profile_niches(["pid-b"])["pid-b"]["name"] == "Deep sea")
check("khong co acc che do 4 -> {}", app.resolve_profile_niches([]) == {})

_orig_ask = ui.messagebox.askyesno
ui.messagebox.askyesno = lambda *a, **k: True
lst.selection_clear(0, "end")
lst.selection_set(1)
lst.event_generate("<<ListboxSelect>>")
root.update()
buttons["Xóa"].invoke()
ui.messagebox.askyesno = _orig_ask
check("xoa niche", [n["name"] for n in app_config.load_config()["niches"]] == ["Deep sea"])
app._toggle_theme()
root.update()
app._toggle_theme()
root.update()
check("doi nen sang/toi khi hop Niche dang mo khong loi", nd.winfo_exists())
buttons["Đóng"].invoke()
check("dong hop -> mo lai duoc", app._niche_dialog is None)

print("    -- run_single_profile gan niche + tran phien")


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


CAP = {}


class FakeWorkflow:
    def __init__(self, **kw):
        CAP["kw"] = kw
        self.session_deadline_s = 0
        self.niche = {}
        self.actions_done = 0
        CAP["wf"] = self

    def run_random_session(self, total_actions=5):
        CAP["ran"] = True


_o = (ui.WarmupWorkflow, ui.BrowserController, ui.adjust_window_bounds, ui.time.sleep)
ui.WarmupWorkflow, ui.BrowserController = FakeWorkflow, FakeController
ui.adjust_window_bounds = lambda *a, **k: None
ui.time.sleep = lambda *_a, **_k: None
THEMES = [{"google_query": "g", "youtube_query": "y"}]
try:
    ui.run_single_profile(FakeAPI(), "pid-run1", "Kenh A1", THEMES, 0, 1920, 1080, False, False, "none",
                          "channel", 0, 0, "", None, "en", niche=saved[0])
    check("phase 'channel' xuong toi WarmupWorkflow", CAP["kw"].get("phase") == "channel" and CAP.get("ran"))
    check("niche duoc gan vao workflow", CAP["wf"].niche.get("name") == "Deep sea")
    check("khong ep tran -> de 0 cho che do 4 tu chon 45-60 phut", CAP["wf"].session_deadline_s == 0)
    check("che do 4 khong bat needs_sub kieu pha 3", CAP["kw"].get("needs_sub") is False)
    ui.run_single_profile(FakeAPI(), "pid-run2", "Kenh A2", THEMES, 0, 1920, 1080, False, False, "none",
                          "channel", 0, 50 * 60, "", None, "en", niche=saved[0])
    check("han muc ngay 50 phut -> tran phien 50 phut (nguong siet cua che do 4 la 60 phut)",
          CAP["wf"].session_deadline_s == 3000, str(CAP["wf"].session_deadline_s))
    ui.run_single_profile(FakeAPI(), "pid-run3", "Acc thuong", THEMES, 0, 1920, 1080, False, False, "none",
                          "clean", 0, 50 * 60, "", None, "en")
    check("pha khac: han muc 50 phut KHONG siet (nguong 30 phut nhu cu)", CAP["wf"].session_deadline_s == 0 and
          CAP["wf"].niche == {})
    ui.run_single_profile(FakeAPI(), "pid-run4", "Kenh A4", THEMES, 0, 1920, 1080, False, False, "none",
                          "channel", 0, 0, "", None, "en")
    check("khong truyen niche -> workflow nhan {} (tam dung tu khoa phien)", CAP["wf"].niche == {})
    ui.NICHE_BY_PID["pid-run5"] = saved[0]
    ui.run_single_profile(FakeAPI(), "pid-run5", "Kenh A5", THEMES, 0, 1920, 1080, False, False, "none",
                          "channel", 0, 0, "", None, "en")
    check("niche chot luc Start (NICHE_BY_PID) toi duoc workflow ma khong doi arity", CAP["wf"].niche.get("name") == "Deep sea")
    ui.NICHE_BY_PID.clear()
finally:
    ui.WarmupWorkflow, ui.BrowserController, ui.adjust_window_bounds, ui.time.sleep = _o

try:
    root.destroy()
except Exception:
    pass

# ---------------------------------------------------------------- [7]
print("\n[7] Tinh")
SRC = open(os.path.join(HERE, "workflow", "channel_mode.py"), encoding="utf-8").read()
CODE = "\n".join(l for l in SRC.split('"""')[2:] and "\n".join(SRC.split('"""')[2:]).splitlines()
                 if not l.strip().startswith("#"))
check("khong co selector o nhap binh luan", all(x not in SRC for x in (
    "#simplebox-placeholder", "#contenteditable-root", "ytd-commentbox", "comment-simplebox", "#submit-button")))
check("khong bam nut dislike / xoa / report", all(x not in CODE for x in ("dislike-button", "Report", "delete")))
for sel in ("button#avatar-btn", "ytd-topbar-menu-button-renderer button", "#filter-button button",
            "ytd-search-filter-group-renderer", "like-button-view-model button",
            "ytd-comment-thread-renderer", "#like-button button", "a[href*='udm=vids']",
            "a[href^='/shorts/'].reel-item-endpoint", "#navigation-button-down button",
            "span.inline-metadata-item", "ytd-masthead a#logo"):
    check(f"selector da diag co mat: {sel}", sel in SRC)
check("moi cho lay toa do di qua _safe_bbox (khong goi bounding_box truc tiep)", "bounding_box(" not in CODE)
check("vong cho URL dung _pump_wait", "_pump_wait" in SRC and "def _ch_wait_url" in SRC)
W = open(os.path.join(HERE, "workflow", "warmup.py"), encoding="utf-8").read()
check("warmup.py: 3 action_map cu con nguyen", W.count('if self.phase == "youtube":') >= 2 and
      'elif self.phase == "mail":' in W and '"action_search_youtube": (self.action_search_youtube, 0.60)' in W)
check("warmup.py: re nhanh che do 4 nam TRUOC khi mo tab",
      W.index('if self.phase == "channel":') < W.index("page = self.context.new_page()", W.index("def run_random_session")))

check("DB that khong doi", _hash(REAL_DB) == REAL_DB_BEFORE)
check("app_config that khong doi", _hash(REAL_CFG) == REAL_CFG_BEFORE)

print(f"\nPASS: {PASS}  FAIL: {FAIL}")
print("SMOKE v1.9.3: ALL PASS" if FAIL == 0 else "SMOKE v1.9.3: CO LOI")
sys.exit(0 if FAIL == 0 else 1)
