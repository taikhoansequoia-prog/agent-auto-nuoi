# -*- coding: utf-8 -*-
"""Smoke test v1.7.8 — DÙNG NHIỀU TỪ KHÓA CỤM HƠN MỖI PHIÊN, NHƯNG GIÃN NHỊP.

User: muốn mỗi phiên dùng nhiều từ khóa hơn, nhưng "phải giãn ra, truy cập quá nhiều là
bot". v1.7.8 KHÔNG rút ngắn nghỉ, KHÔNG thêm điều hướng: trong 1 hành động tìm kiếm
(YouTube / Google Tin tức / Maps), sau khi lướt kết quả có xác suất gõ TÌM LẠI 1-2 từ khóa
kế trong cụm vào chính ô tìm kiếm đang mở, mỗi lần có nghỉ đọc 15-40s + lướt 20-45s.

Chạy OFFLINE: python src\\test_v178.py
"""
import os
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SRC)
for p in (ROOT, SRC):
    if p not in sys.path:
        sys.path.insert(0, p)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ["GPM_BOT_DATA_DIR"] = tempfile.mkdtemp(prefix="gpm_v178_")

import src.workflow.warmup as W  # noqa: E402

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
    def on(self, *a, **k):
        return None


class FakeLocator:
    def __init__(self, page, sel):
        self.page, self.sel = page, sel

    @property
    def first(self):
        return self

    def wait_for(self, **k):
        if self.page.broken:
            raise RuntimeError("box gone")

    def click(self, **k):
        self.page.log.append("click")


class FakeKeyboard:
    def __init__(self, page):
        self.page = page

    def press(self, key):
        self.page.log.append(key)


class FakePage:
    def __init__(self, broken=False):
        self.broken = broken
        self.log = []
        self.sels = []
        self.keyboard = FakeKeyboard(self)

    def locator(self, sel):
        self.sels.append(sel)
        return FakeLocator(self, sel)

    def wait_for_load_state(self, *a, **k):
        pass


class FakeDB:
    def __init__(self):
        self.used = []

    def log_keyword_used(self, pid, kw):
        self.used.append(kw)
        return True


def make_wf(n=5, used=0):
    wf = W.WarmupWorkflow(context=FakeContext(), db_handler=FakeDB(), profile_id="P")
    wf.keyword_cluster = [{"google_query": f"g{i}", "youtube_query": f"y{i}"} for i in range(1, n + 1)]
    wf._cluster_pos = used
    wf.typed = []
    wf.random_sleep = lambda *a, **k: None
    wf._human_scroll = lambda *a, **k: None
    wf.human_type = lambda box, text: wf.typed.append(text)
    return wf, FakePage()


_real_random, _real_uniform = W.random.random, W.random.uniform
W.random.uniform = lambda a, b: 0.0  # vòng lướt 20-45s -> 0 (test không ngồi chờ)


def run(wf, page, roll, platform="youtube", key="youtube_query"):
    W.random.random = lambda: roll
    try:
        return wf._refine_search(page, "input[name='search_query']", platform, key)
    finally:
        W.random.random = _real_random


print("\n== 1. Tìm lại theo cụm")
wf, pg = make_wf(5, used=1)
n = run(wf, pg, 0.0)
check("xác suất trúng cả 2 -> tìm lại 2 lần", n == 2, str(n))
check("gõ đúng 2 từ khóa KẾ TIẾP (YouTube lấy youtube_query)", wf.typed == ["y2", "y3"], str(wf.typed))
check("xoá ô trước khi gõ (Ctrl+A, Backspace) rồi Enter",
      pg.log.count("Control+A") == 2 and pg.log.count("Backspace") == 2 and pg.log.count("Enter") == 2,
      str(pg.log))
check("ghi DB cho phiên sau (google_query)", wf.db.used == ["g2", "g3"], str(wf.db.used))
check("gõ vào CHÍNH ô đã mở (không điều hướng mới)",
      set(pg.sels) == {"input[name='search_query']"}, str(set(pg.sels)))

wf, pg = make_wf(5, used=1)
check("roll 0.5: chỉ lần 1 trúng (0.6) -> 1 lần", run(wf, pg, 0.5) == 1)
wf, pg = make_wf(5, used=1)
check("roll 0.9: không tìm lại", run(wf, pg, 0.9) == 0 and wf.typed == [])
wf, pg = make_wf(5, used=1)
run(wf, pg, 0.0, platform="news", key="google_query")
check("Google/Maps lấy google_query", wf.typed == ["g2", "g3"], str(wf.typed))

print("\n== 2. Giới hạn — không dồn dập")
wf, pg = make_wf(5, used=4)
check("cụm chỉ còn 1 từ chưa dùng -> tối đa 1 lần", run(wf, pg, 0.0) == 1)
wf, pg = make_wf(5, used=5)
check("dùng hết cụm trong phiên -> KHÔNG tìm lại (không vòng lại)", run(wf, pg, 0.0) == 0)
wf, pg = make_wf(5, used=0)
wf._session_end_ts = time.time() + 60
check("phiên còn < 3 phút -> không tìm lại", run(wf, pg, 0.0) == 0)
wf, pg = make_wf(5, used=0)
wf._session_end_ts = time.time() + 3600
check("phiên còn nhiều giờ -> vẫn tìm lại", run(wf, pg, 0.0) == 2)
wf, pg = make_wf(5, used=0)
wf._should_stop_cb = lambda: True
check("bấm DỪNG -> không tìm lại", run(wf, pg, 0.0) == 0)
wf, pg = make_wf(0)
check("không có cụm -> hành vi cũ (0 lần)", run(wf, pg, 0.0) == 0)
wf, pg = make_wf(5, used=0)
pg.broken = True
check("ô tìm kiếm biến mất -> dừng êm, không ném lỗi", run(wf, pg, 0.0) == 0)
check("lỗi ô tìm kiếm không 'đốt' từ khóa", wf._cluster_pos == 0, str(wf._cluster_pos))

print("\n== 3. Nhịp nghỉ (đo trên mã nguồn)")
src = open(os.path.join(SRC, "workflow", "warmup.py"), encoding="utf-8").read()
body = src[src.index("def _refine_search"):src.index("def _plan_keyword")]
check("nghỉ đọc 15-40s trước mỗi lần tìm lại", "self.random_sleep(15, 40)" in body)
check("lướt kết quả 20-45s sau mỗi lần tìm lại", "random.uniform(20, 45)" in body)
check("tối đa 2 lần/hành động", "REFINE_P = (0.6, 0.35)" in src)
check("không rút ngắn nghỉ giữa hành động", "def _sample_action_rest" in src
      and "(120, 240)" in src[src.index("def _sample_action_rest"):][:1500])
for sel, label in (("input[name='search_query']\", \"youtube\"", "YouTube"),
                   ("\"textarea[name='q'], input[name='q']\", \"news\"", "Google Tin tức"),
                   ("\"input[name='q']\", \"maps\"", "Maps")):
    check(f"gắn vào action {label}", sel in src)

W.random.uniform = _real_uniform
print(f"\nPASS: {PASS}   FAIL: {FAIL}")
print("SMOKE v1.7.8: ALL PASS" if FAIL == 0 else "SMOKE v1.7.8: CO LOI")
sys.exit(0 if FAIL == 0 else 1)
