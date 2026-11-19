# -*- coding: utf-8 -*-
"""Smoke test v1.7.9 — GÕ SAI CHÍNH TẢ NGẪU NHIÊN HƠN (human_type).

Trước: chỉ 1 kiểu lỗi (bấm nhầm phím cạnh) và LẦN NÀO cũng sửa ngay.
v1.7.9:
  - mức cẩu thả mỗi lần gõ nhân ngẫu nhiên 0.6-1.8
  - lỗi có sửa thêm kiểu ĐẢO 2 chữ ("teh" -> xoá -> "the")
  - ~10% lần gõ để SÓT 1 lỗi không sửa (nhầm phím / đảo / sót / lặp chữ) rồi Enter luôn

Mô phỏng bàn phím bằng bộ đệm: type() thêm, Backspace xoá, Space thêm ' '.
Chạy OFFLINE: python src\\test_v179.py
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
os.environ["GPM_BOT_DATA_DIR"] = tempfile.mkdtemp(prefix="gpm_v179_")

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


class KB:
    def __init__(self):
        self.buf = []
        self.backspaces = 0

    def type(self, s):
        self.buf.extend(s)

    def press(self, k):
        if k == "Backspace":
            self.backspaces += 1
            if self.buf:
                self.buf.pop()
        elif k == "Space":
            self.buf.append(" ")


class Page:
    def __init__(self):
        self.keyboard = KB()


class Loc:
    def __init__(self):
        self.page = Page()

    def click(self, **k):
        pass


class Ctx:
    def on(self, *a, **k):
        pass


W.time.sleep = lambda *a, **k: None
W.print = lambda *a, **k: None  # im log trong vòng lặp nhiều nghìn lần
wf = W.WarmupWorkflow(context=Ctx())
wf.random_sleep = lambda *a, **k: None


def typed(text, seed, wpm=None):
    wf.rng = random.Random(seed)
    if wpm is not None:
        wf.base_wpm = wpm
    loc = Loc()
    wf.human_type(loc, text)
    kb = loc.page.keyboard
    return "".join(kb.buf), kb.backspaces


def one_edit(a, b):
    """True nếu b khác a đúng 1 lỗi: thay 1 chữ / đảo 2 chữ kề / sót 1 chữ / lặp 1 chữ."""
    if a == b:
        return False
    if len(a) == len(b):
        diff = [k for k in range(len(a)) if a[k] != b[k]]
        if len(diff) == 1:
            return True
        return len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]]
    if len(b) == len(a) - 1:
        return any(a[:k] + a[k + 1:] == b for k in range(len(a)))
    if len(b) == len(a) + 1:
        return any(b[:k] + b[k + 1:] == a and b[k] == b[k - 1] for k in range(1, len(b)))
    return False


TEXT = "best running shoes for beginners"
N = 3000

print("\n== 1. Lỗi không sửa: tần suất + đúng 1 lỗi")
wf.base_wpm = 85
results = [typed(TEXT, s) for s in range(N)]
wrong = [r for r, _bs in results if r != TEXT]
rate = len(wrong) / N
check(f"~10% lần gõ để sót 1 lỗi (đo {rate:.1%})", 0.06 <= rate <= 0.14, f"{len(wrong)}/{N}")
bad = [r for r in wrong if not one_edit(TEXT, r)]
check("mỗi lần sót đúng 1 lỗi (vẫn đọc được)", not bad, str(bad[:3]))
kinds = set()
for r in wrong:
    if len(r) == len(TEXT) - 1:
        kinds.add("drop")
    elif len(r) == len(TEXT) + 1:
        kinds.add("double")
    else:
        diff = [k for k in range(len(TEXT)) if TEXT[k] != r[k]]
        kinds.add("swap" if len(diff) == 2 else "neighbor")
check("đủ 4 kiểu lỗi: nhầm phím / đảo / sót / lặp", kinds == {"neighbor", "swap", "drop", "double"}, str(kinds))
check("không bao giờ sót lỗi ở dấu cách", all(r.count(" ") == TEXT.count(" ") for r in wrong))

print("\n== 2. Lỗi có sửa: kết quả cuối vẫn đúng, có xoá-gõ lại")
fixed = [(r, bs) for r, bs in results if r == TEXT and bs > 0]
check("có nhiều lần gõ sai rồi tự sửa", len(fixed) > N * 0.2, f"{len(fixed)}/{N}")
check("không có kết quả nào hỏng ngoài 1 lỗi để sót", len([r for r, _ in results if r != TEXT and not one_edit(TEXT, r)]) == 0)

print("\n== 3. Mức cẩu thả khác nhau mỗi lần")
wf.base_wpm = 60
bs_counts = [typed(TEXT, s)[1] for s in range(400)]
check("số lần bấm xoá dao động giữa các lần gõ", len(set(bs_counts)) >= 4, str(sorted(set(bs_counts))))

print("\n== 4. Không để sót lỗi khi không hợp lý")
short = [typed("weather", s)[0] for s in range(800)]
check("chữ ngắn < 8 ký tự -> không bao giờ để sót", all(r == "weather" for r in short))
jp = "ウォーキングシューズ おすすめ"
jpr = [typed(jp, s)[0] for s in range(500)]
check("chữ Nhật/Hàn -> không để sót, không đảo chữ", all(r == jp for r in jpr))
vi = "giày chạy bộ tốt nhất cho người mới"
vir = [typed(vi, s)[0] for s in range(1500)]
vi_wrong = [r for r in vir if r != vi]
check("tiếng Việt có dấu: chỉ lỗi ở chữ không dấu, vẫn đúng 1 lỗi",
      all(one_edit(vi, r) for r in vi_wrong), str(vi_wrong[:2]))

print("\n== 5. Tĩnh")
src = open(os.path.join(SRC, "workflow", "warmup.py"), encoding="utf-8").read()
check("TYPO_LEAVE_P = 0.10", "TYPO_LEAVE_P = 0.10" in src)
check("mức cẩu thả 0.6-1.8", "typo_chance *= rng.uniform(0.6, 1.8)" in src)
check("human_type vẫn dùng self.rng (thread-safe)", "rng = self.rng" in src)

print(f"\nPASS: {PASS}   FAIL: {FAIL}")
print("SMOKE v1.7.9: ALL PASS" if FAIL == 0 else "SMOKE v1.7.9: CO LOI")
sys.exit(0 if FAIL == 0 else 1)
