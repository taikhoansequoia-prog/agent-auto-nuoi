# -*- coding: utf-8 -*-
"""Smoke test v1.8.0 — HẾT GIẬT KHI LƯỚT TIKTOK + GÕ MÃ GOOGLE FINANCE KIỂU NGƯỜI.

Đo thật 19/11/2026 (Profile warmup 19/18, feed /foryou): khung #column-list-container có
scroll-snap bắt buộc; lăn 18-30 nấc nhỏ (_human_scroll) -> video nảy 37-59 lần, 0/5 lần sang
video. Bấm nút "Đi đến video tiếp theo" của TikTok -> 6/6 sang đúng 1 video, 0 lần nảy.
Khách chưa đăng nhập còn bị 2 hộp che (đăng nhập / chọn sở thích) -> phải đóng giữa phiên.

Chạy OFFLINE: python src\\test_v180.py
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
os.environ["GPM_BOT_DATA_DIR"] = tempfile.mkdtemp(prefix="gpm_v180_")

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


W.time.sleep = lambda *a, **k: None


class Feed:
    """Trang TikTok giả: scrollTop, nút ↓/↑, hộp che (overlay chặn bấm)."""

    def __init__(self, has_buttons=True, has_container=True, overlay=0, overlay_on_click=None, stuck=False):
        self.st = 0
        self.has_buttons, self.has_container = has_buttons, has_container
        self.overlay = overlay                 # số hộp đang che
        self.overlay_on_click = overlay_on_click or set()  # lần bấm thứ mấy thì hộp bật ra
        self.clicks = 0
        self.closed = 0
        self.stuck = stuck
        self.keys = []
        self.keyboard = self

    def press(self, k):
        self.keys.append(k)

    def type(self, s):
        self.keys.append(s)

    def evaluate(self, js):
        return self.st if self.has_container else None

    def locator(self, sel):
        return Loc(self, sel)


class Loc:
    def __init__(self, page, sel):
        self.page, self.sel = page, sel

    @property
    def first(self):
        return self

    def _is_close(self):
        return self.sel in W.WarmupWorkflow.TIKTOK_OVERLAY_CLOSE_SELS

    def count(self):
        if self._is_close():
            return 1 if self.page.overlay else 0
        return 1 if self.page.has_buttons else 0

    def is_visible(self, timeout=0):
        return self.count() > 0

    def click(self, **k):
        if self._is_close():
            self.page.overlay = max(0, self.page.overlay - 1)
            self.page.closed += 1


def make():
    wf = W.WarmupWorkflow(context=type("C", (), {"on": lambda *a, **k: None})())
    wf.random_sleep = lambda *a, **k: None

    def click(page, loc):
        page.clicks += 1
        if page.clicks in page.overlay_on_click:
            page.overlay += 1          # hộp bật ra, lần bấm này bị nuốt
            return
        if page.overlay or page.stuck:
            return
        page.st += 945 if "next" in loc.sel else -945
    wf.human_click = click
    return wf


print("\n== 1. Chuyển video bằng nút + xác nhận")
wf, pg = make(), Feed()
check("bấm ↓ -> sang đúng 1 video", wf._tiktok_go(pg, "next") is True and pg.st == 945, str(pg.st))
check("chỉ bấm 1 lần khi thành công", pg.clicks == 1)
check("bấm ↑ -> quay lại", wf._tiktok_go(pg, "prev") is True and pg.st == 0)

wf, pg = make(), Feed(overlay=1)
check("hộp đang che -> đóng trước rồi mới bấm", wf._tiktok_go(pg, "next") and pg.closed == 1 and pg.st == 945)

wf, pg = make(), Feed(overlay_on_click={1})
ok = wf._tiktok_go(pg, "next")
check("hộp bật ra đúng lúc bấm -> đóng rồi thử lại 1 lần -> sang", ok and pg.clicks == 2 and pg.st == 945,
      f"clicks={pg.clicks} st={pg.st}")

wf, pg = make(), Feed(stuck=True)
check("feed kẹt -> thử đúng 2 lần rồi trả False (không lặp vô ích)",
      wf._tiktok_go(pg, "next") is False and pg.clicks == 2, str(pg.clicks))

wf, pg = make(), Feed(has_buttons=False)
r = wf._tiktok_go(pg, "next")
check("bố cục không có nút -> dùng phím ArrowDown", "ArrowDown" in pg.keys, str(pg.keys))
wf, pg = make(), Feed(has_buttons=False, has_container=False)
check("không đo được khung feed -> coi là đã sang (không chặn)", wf._tiktok_go(pg, "next") is True)
wf, pg = make(), Feed(has_buttons=False)
check("không có nút ↑ -> quay lại trả False", wf._tiktok_go(pg, "prev") is False)

print("\n== 2. Đóng hộp che")
wf, pg = make(), Feed(overlay=2)
n = wf._tiktok_dismiss_overlays(pg)
check("đóng được các hộp đang che", n >= 1 and pg.overlay == 0, f"n={n}")
wf, pg = make(), Feed()
check("không có hộp -> 0", wf._tiktok_dismiss_overlays(pg) == 0)
sels = W.WarmupWorkflow.TIKTOK_OVERLAY_CLOSE_SELS
check("có selector hộp đăng nhập + hộp chọn sở thích (đo DOM thật)",
      '[data-e2e="modal-close-inner-button"]' in sels and any("CloseButtonWrapper" in s for s in sels))

print("\n== 3. Mã nguồn action_watch_tiktok")
src = open(os.path.join(SRC, "workflow", "warmup.py"), encoding="utf-8").read()
blk = src[src.index("    def action_watch_tiktok"):src.index("    def action_read_wikipedia")]
check("không còn lăn _human_scroll trong TikTok", "_human_scroll(" not in blk)
check("không còn probe nửa màn hình", "uniform(0.4, 0.7)" not in blk)
check("chuyển video qua _tiktok_go + dừng khi kẹt",
      'if not self._tiktok_go(page, "next"):' in blk and "break" in blk)
check("có quay lại video trước (~10%)", "random.random() < 0.10" in blk and '_tiktok_go(page, "prev")' in blk)
check("đóng hộp che ở đầu mỗi video", "self._tiktok_dismiss_overlays(page)" in blk)
check("giữ thời lượng xem 3 tầng", "int(random.uniform(45, 90))" in blk and "int(random.uniform(4, 12))" in blk)
check("giữ nghỉ sau mỗi lần chuyển (giãn nhịp)", "self.random_sleep(2, 4)" in blk)
check("selector nút đo từ DOM thật", 'feed-navigation-next' in src and 'feed-navigation-prev' in src)

print("\n== 4. Google Finance gõ mã kiểu người")


class KB:
    def __init__(self):
        self.buf = []

    def type(self, s):
        self.buf.extend(s)

    def press(self, k):
        if k == "Backspace" and self.buf:
            self.buf.pop()
        elif k == "Space":
            self.buf.append(" ")


class KPage:
    def __init__(self):
        self.keyboard = KB()


wf = make()
W.print = lambda *a, **k: None
outs = set()
for s in range(300):
    wf.rng = random.Random(s)
    kp = KPage()
    wf.human_type_keys(kp, "BTC-USD")
    outs.add("".join(kp.keyboard.buf))
del W.print
check("mã luôn đúng sau khi gõ (lỗi đều được sửa, mã ngắn không để sót)", outs == {"BTC-USD"}, str(outs))
fin = src[src.index("    def action_google_finance"):]
fin = fin[:fin.index("\n    def ", 10)]
check("Finance dùng human_type_keys", "self.human_type_keys(page, query)" in fin)
check("Finance bỏ vòng gõ thô từng ký tự", "for char in query:" not in fin)

print(f"\nPASS: {PASS}   FAIL: {FAIL}")
print("SMOKE v1.8.0: ALL PASS" if FAIL == 0 else "SMOKE v1.8.0: CO LOI")
sys.exit(0 if FAIL == 0 else 1)
