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

print()
print("=" * 68)
print(f"KET QUA: PASS: {PASS}   FAIL: {FAIL}")
print("=" * 68)
print("SMOKE v1.4.5: " + ("ALL PASS" if FAIL == 0 else f"{FAIL} FAIL"))
sys.exit(1 if FAIL else 0)
