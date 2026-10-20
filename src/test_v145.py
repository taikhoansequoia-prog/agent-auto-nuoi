# -*- coding: utf-8 -*-
"""Smoke test v1.4.5 — kiểm tra 4 fix của vòng E2E start-to-end 16/10/2026:

  #1 action_watch_tiktok: tỷ lệ dừng trỏ chuột ngắm video 0.5 -> 0.75 + liếc thumb kế
  #2 _preview_sweep_browse: MỌI thumb được pick đều phải được human_hover
     (trước đây nhánh mode_roll < 0.25 bỏ qua hover -> ~25% thumb không hề được trỏ)
  #3 _close_popups: chống flood log (memo selector) + không còn `except: pass` trần,
     mỗi element lỗi không làm mất các element còn lại
  #4 action_watch_video: không in "Sẽ lướt xem trước 1 lượt" (số nhiều) khi chỉ 1 lượt

Cách chạy:  python src\\test_v145.py
"""
import io
import os
import random
import sys
import contextlib

SRC = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SRC)
for p in (ROOT, SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

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


# =====================================================================
# 1. _preview_sweep_browse — mọi thumb pick đều phải được hover
# =====================================================================
class FakeEl:
    def __init__(self, i):
        self.i = i

    def __repr__(self):
        return f"<El{self.i}>"


class SweepSelf:
    """Self giả (duck-typing) để gọi thẳng WarmupWorkflow._preview_sweep_browse."""

    def __init__(self):
        self.hovers = []          # element được human_hover
        self.scroll_els = []      # element được cuộn tới
        self.scroll_dists = []    # smooth_scroll theo px
        self.sweeps = []          # thời lượng dừng
        self.viewport_moves = 0

    def _smooth_scroll_to_element(self, page, el):
        self.scroll_els.append(el)

    def human_hover(self, page, el):
        self.hovers.append(el)

    def random_sleep(self, a, b):
        self.sweeps.append(round(random.uniform(a, b), 2))

    def move_mouse_viewport_center(self, page):
        self.viewport_moves += 1

    def smooth_scroll(self, page, dist):
        self.scroll_dists.append(dist)


print("=" * 68)
print("1. _preview_sweep_browse: moi thumb duoc pick PHAI duoc tro chuot")
print("=" * 68)
random.seed(20261016)
bad_no_hover = 0
bad_less2 = 0
bad_order = 0
for trial in range(400):
    n = random.randint(2, 12)  # caller luon co it nhat 2 thumb
    els = [FakeEl(i) for i in range(n)]
    s = SweepSelf()
    WarmupWorkflow._preview_sweep_browse(s, None, els)
    if len(s.hovers) != len(s.scroll_els):
        bad_no_hover += 1
    if len(s.hovers) < 2:
        bad_less2 += 1
    # cuon toi thumb nao thi phai ngam thumb do, cung thu tu
    if s.hovers != s.scroll_els:
        bad_order += 1
check("400 lan chay: so thumb HOVER == so thumb CUON TOI", bad_no_hover == 0,
      f"{bad_no_hover} lan lech")
check("luon tro >= 2 thumb (sweep_count 2..5)", bad_less2 == 0, f"{bad_less2} lan <2")
check("thu tu dung: cuon toi thumb nao thi ngam thumb do", bad_order == 0,
      f"{bad_order} lan sai thu tu")

s = SweepSelf()
WarmupWorkflow._preview_sweep_browse(s, None, [FakeEl(i) for i in range(40)])
check("list lon 40 thumb: 2..5 thumb duoc tro, khong thumb nao bi bo qua",
      2 <= len(s.hovers) <= 5 and len(s.hovers) == len(s.scroll_els),
      f"hover={len(s.hovers)} scroll={len(s.scroll_els)}")

s = SweepSelf()
WarmupWorkflow._preview_sweep_browse(s, None, [FakeEl(i) for i in range(10)])
check("thoi luong dung ngau nhien (khong phai 1 gia tri co dinh)", len(set(s.sweeps)) >= 2,
      f"{sorted(set(s.sweeps))[:6]}")

s = SweepSelf()
WarmupWorkflow._preview_sweep_browse(s, None, [FakeEl(0)])
check("list 1 thumb: van tro dung 1 thumb, khong crash",
      len(s.hovers) == 1 and s.hovers == s.scroll_els,
      f"hover={len(s.hovers)} scroll={len(s.scroll_els)}")

s = SweepSelf()
WarmupWorkflow._preview_sweep_browse(s, None, [])
check("list rong: khong crash, khong hover", s.hovers == [] and s.scroll_els == [])

# =====================================================================
# 2. _close_popups — memo selector + đếm nút + không nuốt cả vòng lặp
# =====================================================================
class FakeBtn:
    def __init__(self, fail=False):
        self.fail = fail
        self.clicked = 0

    def click(self, timeout=None):
        if self.fail:
            raise RuntimeError("stale element")
        self.clicked += 1


class FakeLoc:
    def __init__(self, btns):
        self._btns = btns

    def all(self):
        return list(self._btns)


class FakePage:
    """Trả về button khớp cho đúng selector được chỉ định."""

    def __init__(self, mapping):
        self.mapping = mapping  # {seed_selector: [FakeBtn,...]}
        self.lookups = []

    def locator(self, full):
        seed = full[: -len(":visible")] if full.endswith(":visible") else full
        self.lookups.append(seed)
        # Khop theo tien to: mo phong dung "selector dau tien khop trong danh sach
        # uu tien cua _close_popups se thang" (Playwright that cung match tien to nhu vay).
        for prefix, btns in self.mapping.items():
            if seed == prefix or seed.startswith(prefix):
                return FakeLoc(btns)
        return FakeLoc([])


class PopupSelf:
    def __init__(self):
        self._popup_sel_memo = None
        self.sleeps = 0

    def random_sleep(self, a, b):
        self.sleeps += 1


def run_close_popups(page, self_obj):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        WarmupWorkflow._close_popups(self_obj, page)
    return buf.getvalue()


print()
print("=" * 68)
print("2. _close_popups: chong flood log + chiu loi tung nut")
print("=" * 68)
btn_a1, btn_a2 = FakeBtn(), FakeBtn()
page = FakePage({"#dismiss-button": [btn_a1, btn_a2]})
s = PopupSelf()

out1 = run_close_popups(page, s)
check("lan 1: in dung 1 dong [+] Phat hien selector", out1.count("[+] Ph\u00e1t hi\u1ec7n") == 1,
      f"count={out1.count('[+] Ph\u00e1t hi\u1ec7n')}")
check("lan 1: KHONG in dong [+] cho tung element (2 nut -> van 1 dong)",
      out1.count("[+] Ph\u00e1t hi\u1ec7n") == 1)
check("lan 1: in dong tong ket 'Da dong 2 nut'", "\u0110\u00e3 \u0111\u00f3ng 2" in out1)
check("lan 1: da bam ca 2 nut", btn_a1.clicked == 1 and btn_a2.clicked == 1,
      f"{btn_a1.clicked}/{btn_a2.clicked}")

out2 = run_close_popups(page, s)
check("lan 2 (cung selector): KHONG in lai dong [+] Phat hien",
      out2.count("[+] Ph\u00e1t hi\u1ec7n") == 0, repr(out2.strip()[:70]))
check("lan 2: van in tong ket (van dong popup that)", "\u0110\u00e3 \u0111\u00f3ng 2" in out2)
check("lan 2: van thuc su click", btn_a1.clicked == 2 and btn_a2.clicked == 2)

s3 = PopupSelf()
page3 = FakePage({"#dismiss-button": [FakeBtn(), FakeBtn()]})
consecutive = "\n".join(run_close_popups(page3, s3) for _ in range(19))
check("lap 19 vong doc bai: tong dong '[+] Phat hien' = 1 (truoc fix: 38)",
      consecutive.count("[+] Ph\u00e1t hi\u1ec7n") == 1,
      f"count={consecutive.count('[+] Ph\u00e1t hi\u1ec7n')}")

# selector UU TIEN (dau danh sach) luon co mat -> khong bao gio bao selector sau
page4 = FakePage({"#dismiss-button": [FakeBtn()], "[aria-label='Close']": [FakeBtn()]})
s4 = PopupSelf()
out_a = run_close_popups(page4, s4)
out_b = run_close_popups(page4, s4)
check("2 nut khac selector: 1 lan goi -> toi da 1 dong bao du 2 selector cung khop",
      out_a.count("[+] Ph\u00e1t hi\u1ec7n") == 1, f"count={out_a.count('[+] Ph\u00e1t hi\u1ec7n')}")
check("2 nut khac selector: lan goi sau im lang (memo da giu)",
      out_b.count("[+] Ph\u00e1t hi\u1ec7n") == 0)
check("dong tong ket liet ke DU MOI selector da bam (khong chi selector cuoi)",
      "#dismiss-button" in out_a and "[aria-label='Close']" in out_a)
check("dong tong ket dung so nut", "\u0110\u00e3 \u0111\u00f3ng 2 n\u00fat" in out_a)

# chi con selector sau -> phai bao lai (memo doi)
s5 = PopupSelf()
s5._popup_sel_memo = "#dismiss-button"
page5 = FakePage({"[aria-label='Close']": [FakeBtn()]})
out5 = run_close_popups(page5, s5)
check("popup doi loai: memo doi -> bao lai dung selector moi",
      out5.count("[+] Ph\u00e1t hi\u1ec7n") == 1 and "[aria-label='Close']" in out5,
      repr(out5.strip()[:80]))

page6 = FakePage({"#dismiss-button": [FakeBtn(fail=True), FakeBtn(), FakeBtn()]})
s6 = PopupSelf()
ok, err = True, ""
try:
    out6 = run_close_popups(page6, s6)
except Exception as e:  # pragma: no cover
    ok, err = False, str(e)
check("nut loi (stale) khong nem exception ra ngoai", ok, err)
check("nut loi van cho cac nut sau chay tiep", ok and "\u0110\u00e3 \u0111\u00f3ng 2" in out6,
      repr(out6.strip()[-45:]))

s7 = PopupSelf()
out7 = run_close_popups(FakePage({}), s7)
check("khong co popup: im lang hoan toan", out7.strip() == "", repr(out7))

# =====================================================================
# 3. Kiểm tra tĩnh trên source (các nhánh không thể dựng stub)
# =====================================================================
print()
print("=" * 68)
print("3. Kiem tra tinh source (TikTok 0.75 + liec thumb ke, print 1 luot)")
print("=" * 68)
src_path = os.path.join(SRC, "workflow", "warmup.py")
with io.open(src_path, encoding="utf-8") as f:
    code = f.read()

tiktok = code.split("def action_watch_tiktok")[1].split("def action_read_wikipedia")[0]
check("TikTok: ty le dung tro chuot la 0.75", "if random.random() < 0.75:" in tiktok)
check("TikTok: co comment giai thich nang 0.5 -> 0.75",
      "n\u00e2ng t\u1ef7 l\u1ec7 0.5 -> 0.75" in tiktok)
check("TikTok: co liec sang thumb video ke tiep",
      'page.locator("video:visible").nth(1)' in tiktok)
check("TikTok: van giu nhip tim '...dang xem video'", "...\u0111ang xem video" in tiktok)
check("TikTok: van giu nhanh 'Quet nhe xem truoc video ke'",
      "xem tr\u01b0\u1edbc video k\u1ebf r\u1ed3i k\u00e9o v\u1ec1" in tiktok)
check("TikTok: van giu 'Dung chut, tro chuot ngam video dang xem'",
      "\u0111ang xem (ki\u1ec3u xem l\u01b0\u1edbt)" in tiktok)
check("TikTok: van giu cuon sang video tiep theo",
      "Cu\u1ed9n sang video ti\u1ebfp theo" in tiktok)

sweep = code.split("def _preview_sweep_browse")[1].split("def action_watch_tiktok")[0]
sweep_doc = sweep.split('"""')[1]
check("_preview_sweep_browse: docstring KHONG con khang dinh sai 'Dung chung ... TikTok'",
      "D\u00f9ng chung cho trang ch\u1ee7" not in sweep_doc, repr(sweep_doc[:46]))
check("_preview_sweep_browse: docstring noi ro CHI dung cho YouTube",
      "CH\u1ec8 d\u00f9ng cho trang ch\u1ee7 YouTube" in sweep_doc)
check("_preview_sweep_browse: nhanh luot voi co human_hover ngay sau scroll",
      "self._smooth_scroll_to_element(page, el)\n"
      "                        self.human_hover(page, el)\n"
      "                        self.random_sleep(0.3, 0.8)" in sweep)
check("_preview_sweep_browse: ca 3 nhanh deu co human_hover",
      sweep.count("self.human_hover(page, el)") >= 3,
      f"count={sweep.count('self.human_hover(page, el)')}")

popup = code.split("def _close_popups")[1].split("def _generate_bezier_path")[0]
check("_close_popups: dung memo self._popup_sel_memo", "_popup_sel_memo" in popup)
check("_close_popups: co dong tong ket so nut",
      "\u0110\u00e3 \u0111\u00f3ng {clicked} n\u00fat popup" in popup)
check("_close_popups: KHONG con except tran",
      "except:" not in popup.replace("except Exception:", "@@"))
check("_close_popups: co >=2 except Exception (tung nut + ngoai)",
      popup.count("except Exception") >= 2, f"count={popup.count('except Exception')}")
check("_close_popups: co liet ke moi selector da bam (sels_hit)",
      "sels_hit.append(selector)" in popup and "', '.join(sels_hit)" in popup)
check("_close_popups: co 'continue' khi 1 nut loi (khong break ca vong)",
      "clicked += 1" in popup and "continue" in popup)

init_block = code.split("def _safe_bbox")[0]
check("warmup.py: self._popup_sel_memo = None duoc khoi tao trong __init__",
      "self._popup_sel_memo = None" in init_block)

check("action_watch_video: print 'luot' duoc gate theo num_sweeps > 1",
      "if num_sweeps > 1:" in code)
check("action_watch_video: co nhanh so it cho 1 luot",
      "S\u1ebd l\u01b0\u1edbt xem tr\u01b0\u1edbc 1 l\u01b0\u1ee3t r\u1ed3i ch\u1ed1t video" in code)
sg = code.split("def action_search_google")[1].split("def ")[0]
check("action_search_google: co canh bao dead-code (khong nam trong action_map)",
      "KH\u00d4NG n\u1eb1m trong action_map" in sg and "code ch\u1ebft" in sg)

# =====================================================================
# 4. v1.4.6 — _parse_time tra 0 khi rỗng + clamp 2 vòng xem + nhãn log mới
# =====================================================================
print()
print("=" * 68)
print("4. v1.4.6: _parse_time / clamp watch / nhan cong Google")
print("=" * 68)

# _parse_time không đụng self -> gọi thẳng unbound
pt = WarmupWorkflow._parse_time
check("_parse_time('') == 0 (truoc day == 120, lam chet fallback 180-300s)",
      pt(None, "") == 0, repr(pt(None, "")))
check("_parse_time(None) == 0 (khong crash)", pt(None, None) == 0)
check("_parse_time('4:30') == 270 (giu hanh vi mm:ss)", pt(None, "4:30") == 270)
check("_parse_time('1:02:03') == 3723 (giu hanh vi h:mm:ss)", pt(None, "1:02:03") == 3723)
check("_parse_time('abc') == 0 (ValueError -> 0, khong crash)", pt(None, "abc") == 0)
check("_parse_time('99') == 0 (1 thanh -> 0)", pt(None, "99") == 0)
check("_watch_single_video_logic: fallback random(180,300) van con sau _parse_time",
      "total_seconds = random.randint(180, 300)" in code)

ttk_blk = code.split("def action_watch_tiktok")[1].split("def action_read_wikipedia")[0]
check("TikTok: chunk xem duoc clamp theo thoi gian con lai (khong con (30/27s))",
      "chunk = min(random.uniform(3, 6), watch_time - watched)" in ttk_blk)

wsv = code.split("def _watch_single_video_logic")[1]
wsv = wsv.split("\n    def ")[0]
check("YouTube: giac nghi clamp theo remaining (nap = min(uniform(4,8), remaining))",
      "nap = min(random.uniform(4, 8), remaining)" in wsv)
check("YouTube: co guard remaining <= 0 -> break",
      "if remaining <= 0:" in wsv and "break" in wsv)
check("YouTube: clamp chi dung trong vong xem (time.sleep(nap))",
      "time.sleep(nap)" in wsv)
# v1.4.7: cap thoi luong xem/video + nhip tim chong "dung im"
check("YouTube v1.4.7: cap watch_seconds (video ngan giu %, video dai bo do)",
      "cap_seconds = random.randint(240, 420)" in wsv
      and "watch_seconds > cap_seconds" in wsv
      and "watch_seconds = cap_seconds" in wsv)
check("YouTube v1.4.7: nhan 'bo do - cap' chi in khi bi cap",
      "(b\u1ecf d\u1edf \u2014 cap" in wsv and "if capped:" in wsv)
check("YouTube v1.4.7: nhip tim in deu trong vong xem ( nhu TikTok )",
      "...\u0111ang xem video YouTube (" in wsv
      and "next_beat = watched + random.uniform(20, 30)" in wsv)

nav = code.split("def _navigate_via_google")[1].split("\n    def ")[0]
check("Cong Google: nhan 'Tab dang o Google san' khi url da la google.com",
      'if "google.com" in (page.url or "")' in nav
      and "Tab \u0111ang \u1edf Google" in nav)
check("Cong Google: van goto google.com fresh SERP (khong doi logic dieu huong)",
      'page.goto("https://www.google.com"' in nav)

fin = code.split("def action_google_finance")[1].split("def ")[0]
check("Finance: nhan 'Dich la chinh Google - vao thang' (ro, khong hieu nham bo cong)",
      "\u0110\u00edch l\u00e0 ch\u00ednh Google (Finance)" in fin)
wth = code.split("def action_search_weather")[1].split("def ")[0]
check("Weather: nhan '(dich la chinh Google - hop le)' o nhanh Omnibox",
      "\u0111\u00edch l\u00e0 ch\u00ednh Google \u2014 h\u1ee3p l\u1ec7" in wth)
wv = code.split("def action_watch_video")[1].split("def ")[0]
check("YouTube-home: nhan 'vao thang (site dich, co y)'",
      "site \u0111\u00edch, c\u1ed1 \u00fd" in wv)
check("TikTok guard feed trong: noi ro 'khong phai bo cong Google'",
      "\u0111\u00edch v\u1eabn l\u00e0 TikTok \u2014 kh\u00f4ng ph\u1ea3i b\u1ecf c\u1ed5ng Google" in ttk_blk)
check("action_read_news KHONG bi dong (giu check tinh cua test_v141)",
      "(Fallback Google)" in code.split("def action_read_news")[1].split("def ")[0])

# =====================================================================
# 5. v1.5.1 — TikTok "giật": _human_scroll ease + watch time ngau nhien
#    + human_hover jitter khong con nhay coc
# =====================================================================
print()
print("=" * 68)
print("5. v1.5.1: _human_scroll / watch-time mixture / hover jitter")
print("=" * 68)

import time as _time  # noqa: E402


class ScrollPage:
    """Chi co mouse.wheel — du cho _human_scroll / smooth_scroll dung."""
    def __init__(self):
        self.deltas = []
        self.stamps = []

    class _M:
        def __init__(self, owner):
            self.owner = owner

        def wheel(self, dx, dy):
            self.owner.deltas.append(dy)
            self.owner.stamps.append(_time.monotonic())

    @property
    def mouse(self):
        return ScrollPage._M(self)


hs = code.split("def _human_scroll")[1].split("\n    def ")[0]
check("v1.5.1: co helper _human_scroll (khong sua smooth_scroll - 36 caller khac)",
      "def _human_scroll(self, page, distance" in code)
check("v1.5.1: _human_scroll nhieu buoc hon smooth_scroll (18-30 vs 8-15)",
      "steps = random.randint(18, 30)" in hs and "steps = random.randint(8, 15)" not in hs)
check("v1.5.1: _human_scroll co nhip ease (cham-dau / nhanh-giua / cham-cuoi)",
      "ease = 0.35 + 0.65 * (abs(t - 0.5) * 2) ** 1.5" in hs)
check("v1.5.1: _human_scroll co settle cho scroll-snap on dinh",
      "if settle:" in hs and "time.sleep(random.uniform(0.5, 1.1))" in hs)
check("v1.5.1: smooth_scroll GIU NGUYEN nguyen van (khong bi doi hanh vi)",
      'def smooth_scroll(self, page, distance):' in code
      and "time.sleep(random.uniform(0.02, 0.08))" in code.split("def smooth_scroll")[1].split("\n    def ")[0])

# --- do THAT: _human_scroll phai cham hon smooth_scroll + ease that su ---
sp = ScrollPage()
_t0 = _time.monotonic()
WarmupWorkflow._human_scroll(None, sp, 1000)
dur_hs = _time.monotonic() - _t0
n_steps = len(sp.deltas)
total = sum(sp.deltas)
gaps = [sp.stamps[i + 1] - sp.stamps[i] for i in range(len(sp.stamps) - 1)]
mid = len(gaps) // 2
edge = (gaps[:3] + gaps[-3:])
mean_edge = sum(edge) / len(edge)
mean_mid = sum(gaps[mid - 2:mid + 3]) / 5

check("v1.5.1 do that: _human_scroll(1000px) tai >=1.2s (truoc day 0.2-1.2s)",
      dur_hs >= 1.2, f"{dur_hs:.2f}s")
check("v1.5.1 do that: _human_scroll di dung 18-30 khac",
      18 <= n_steps <= 30, f"{n_steps} khac")
check("v1.5.1 do that: tong quang cuon = distance (khong thieu/thua)",
      abs(total - 1000) < 1e-6, f"{total:.1f}")
check("v1.5.1 do that: nhip dau/cuoi cham hon giua (co ease that)",
      mean_edge > mean_mid * 1.1, f"edge {mean_edge*1000:.0f}ms vs mid {mean_mid*1000:.0f}ms")

sp2 = ScrollPage()
_t0 = _time.monotonic()
WarmupWorkflow.smooth_scroll(None, sp2, 1000)
dur_ss = _time.monotonic() - _t0
check("v1.5.1 do that: _human_scroll cham hon smooth_scroll cung quang duong",
      dur_hs > dur_ss, f"human {dur_hs:.2f}s vs smooth {dur_ss:.2f}s")

sp3 = ScrollPage()
WarmupWorkflow._human_scroll(None, sp3, -250)
check("v1.5.1 do that: _human_scroll chieu NGUOC (keo ve) van chay",
      abs(sum(sp3.deltas) + 250) < 1e-6 and len(sp3.deltas) >= 18,
      f"{len(sp3.deltas)} khac, tong {sum(sp3.deltas):.0f}")

# --- TikTok: khong con smooth_scroll, co _human_scroll ---
check("v1.5.1: TikTok khong con goi smooth_scroll (nguon git chinh)",
      "self.smooth_scroll(" not in ttk_blk)
check("v1.5.1: TikTok dung _human_scroll cho ca 3 cuon (probe x2 + chuyen video)",
      ttk_blk.count("self._human_scroll(") == 3,
      f"{ttk_blk.count('self._human_scroll(')} call site")
check("v1.5.1: cuon chuyen video van du 1 viewport + 50-200px",
      "self._human_scroll(page, vh + random.randint(50, 200))" in ttk_blk)
check("v1.5.1: probe van xuong 0.4-0.7 vh roi keo NGUOC 100-300px",
      "self._human_scroll(page, int(vh * random.uniform(0.4, 0.7)))" in ttk_blk
      and "self._human_scroll(page, -random.randint(100, 300))" in ttk_blk)

# --- watch time: khong con phoi deu 12-35s ---
check("v1.5.1: BO phoi deu random.uniform(12, 35) (E2E ra 27/27/32/24/20/21s)",
      "random.uniform(12, 35)" not in ttk_blk)
check("v1.5.1: co 3 nhanh hanh vi (liec nhanh / xem vua / xem lau)",
      "int(random.uniform(4, 12))" in ttk_blk
      and "int(random.uniform(15, 35))" in ttk_blk
      and "int(random.uniform(45, 90))" in ttk_blk)
check("v1.5.1: xac suat cong don = 1.0 (0.45 / 0.83 / con lai)",
      "if roll < 0.45:" in ttk_blk and "elif roll < 0.83:" in ttk_blk)
check("v1.5.1: watch_time la so NGUYEN (het in 27.4133 thanh '27')",
      "watch_time = int(" in ttk_blk)
check("v1.5.1: nhan hanh vi in ra trong log ('liếc nhanh'...)",
      '"li\u1ebfc nhanh"' in ttk_blk and '"xem v\u1eeba"' in ttk_blk
      and '"xem l\u00e2u' in ttk_blk)
check("v1.5.1: heartbeat dung min() de khong in (13/12s)",
      "({min(watched, watch_time):.0f}/{watch_time:.0f}s)" in ttk_blk)
check("v1.5.1: clamp chunk van NGUYEN VAN (kha nang v1.4.6 giu)",
      "chunk = min(random.uniform(3, 6), watch_time - watched)" in ttk_blk)
check("v1.5.1: vong xem TikTok khong con dong move_mouse bi LAP (2 nhanh roi)",
      ttk_blk.count("if random.random() < 0.3:\n                        self.move_mouse_viewport_center(page)") == 1
      and ttk_blk.count("except Exception:\n                            self.move_mouse_viewport_center(page)") == 1)
check("v1.5.1: tong so move_mouse_viewport_center trong action = 3 (lang dau + 2 nhanh)",
      ttk_blk.count("self.move_mouse_viewport_center(page)") == 3,
      f"{ttk_blk.count('self.move_mouse_viewport_center(page)')} call site")

# --- human_hover: jitter khong con nhay coc ---
hh = code.split("def human_hover")[1].split("\n    def ")[0]
check("v1.5.1: human_hover bo bien do 10px (nhay coc toi 14px cheo)",
      "random.uniform(-10, 10)" not in hh)
check("v1.5.1: human_hover bien do 3px",
      "random.uniform(-3, 3)" in hh)
check("v1.5.1: human_hover noi suy 3-5 buoi giua 2 diem rung",
      "sub = random.randint(3, 5)" in hh and "ratio = s / sub" in hh)
check("v1.5.1: human_hover nghi 0.25-0.7s giua cac nhip (truoc 0.1-0.4s)",
      "time.sleep(random.uniform(0.25, 0.7))" in hh)
check("v1.5.1: human_hover van cap _last_x/_last_y (khong sinh nhay coc lan sau)",
      "page.mouse._last_x = target_x" in hh and "page.mouse._last_y = target_y" in hh)
check("v1.5.1: human_hover van guard _safe_bbox (chong treo 30s v1.4.3)",
      "if not self._safe_bbox(element, timeout=2000):" in hh)

# --- hanh vi THAT: hover khong con mot cu move nhay coc ---
class HoverMouse:
    def __init__(self):
        self.moves = []
        # Pre-seed o dung tam phan tu (400+200/2, 300+100/2) vi move_mouse_bezier
        # da bi stub no-op -> khong dem cu "bay toi element" thanh nhay coc.
        self._last_x = 500.0
        self._last_y = 350.0

    def move(self, x, y):
        if self._last_x is not None:
            self.moves.append((abs(x - self._last_x), abs(y - self._last_y)))
        self._last_x, self._last_y = x, y


class HoverEl:
    def bounding_box(self, timeout=None):
        return {"x": 400, "y": 300, "width": 200, "height": 100}


class HoverPage:
    def __init__(self):
        self.mouse = HoverMouse()


hp = HoverPage()
random.seed(20261020)
try:
    WarmupWorkflow.human_hover.__wrapped__
except Exception:
    pass

# move_mouse_bezier can _generate_bezier_path + sleep; goi truc tiep phan jitter
# bang cach monkeypatch move_mouse_bezier thanh no-op.
class HoverSelf:
    move_mouse_bezier = lambda self, page, element: None
    random_sleep = lambda self, a, b: None
    _safe_bbox = lambda self, element, timeout=1500: element.bounding_box(timeout=timeout)


WarmupWorkflow.human_hover(HoverSelf(), hp, HoverEl())
big = [m for m in hp.mouse.moves if max(m) > 4.0]
check("v1.5.1 do that: human_hover khong con cu move >4px (nhay coc)",
      not big, f"{len(hp.mouse.moves)} move, {len(big)} lon")
check("v1.5.1 do that: human_hover sinh nhieu buoc noi suy (>6)",
      len(hp.mouse.moves) > 6, f"{len(hp.mouse.moves)} buoc")

print()
print("=" * 68)
print(f"KET QUA: PASS: {PASS}   FAIL: {FAIL}")
print("=" * 68)
print("SMOKE v1.4.5+v1.4.6+v1.5.1: " + ("ALL PASS" if FAIL == 0 else f"{FAIL} FAIL"))
sys.exit(1 if FAIL else 0)
