# -*- coding: utf-8 -*-
"""Smoke test v1.8.2 — LUÔN THÔNG BÁO lịch chặn trùng proxy (hộp xác nhận + thanh trạng thái + log).

Chạy OFFLINE: python src\\test_v182.py
"""
import io
import os
import sys
import tempfile
import threading
import time
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
os.environ["GPM_BOT_DATA_DIR"] = tempfile.mkdtemp(prefix="gpm_v182_")

import tkinter as tk  # noqa: E402
from tkinter import ttk  # noqa: E402
import src.ui_main as ui  # noqa: E402

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


PM = {"A1": "1.1.1.1:1:u:p", "A2": "1.1.1.1:1:u:p", "A3": "1.1.1.1:2:u:p",
      "B1": "2.2.2.2:1:u:p", "C1": "3.3.3.3:1:u:p", "N1": ""}

print("\n== 1. Nội dung tóm tắt")
lines = ui.proxy_summary_lines(list(PM), PM, 4)
txt = "\n".join(lines)
check("dòng đầu: BẬT + số profile/proxy", lines[0].startswith("Chặn trùng proxy: BẬT — 6 profile / 3 proxy"), lines[0])
check("ghi số không proxy", "(1 không proxy)" in lines[0])
check("liệt kê proxy dùng chung + chạy LẦN LƯỢT", "1 proxy dùng chung" in txt and "LẦN LƯỢT" in txt and "1.1.1.1: 3 profile" in txt, txt)
check("cảnh báo dư luồng khi luồng > số proxy",
      any("dư" in l for l in ui.proxy_summary_lines(list(PM), PM, 8)))
one = ui.proxy_summary_lines(["B1", "C1"], PM, 2)
check("không trùng -> nói rõ không ai phải chờ", any("không profile nào phải chờ" in l for l in one), str(one))
off = ui.proxy_summary_lines(list(PM), {}, 4, "BitBrowser chưa hỗ trợ đọc proxy")
check("TẮT -> nói rõ lý do", off[0].startswith("Chặn trùng proxy: TẮT — BitBrowser"), off[0])
check("fetch_proxy_map BitBrowser -> TẮT có lý do", ui.fetch_proxy_map(ui.BROWSER_BITBROWSER)[1] != "")

print("\n== 2. Log mỗi lần giữ / chờ / tới lượt / nhả")
ui._PROXY_MAP.clear()
ui._PROXY_MAP.update(PM)
ui._PROXY_BUSY.clear()
ui._PROXY_WAITING.clear()
ui._PROXY_STATE.update(on=True, why="", n_proxy=3)
ui.STOP_EVENT.clear()
buf = io.StringIO()
with redirect_stdout(buf):
    ui._acquire_proxy("A1")
    th = threading.Thread(target=ui._acquire_proxy, args=("A2",))
    th.start()
    time.sleep(0.8)
    waiting_now = dict(ui._PROXY_WAITING)
    ui._release_proxy("A1")
    th.join(3)
    ui._release_proxy("A2")
    ui._acquire_proxy("N1")
log = buf.getvalue()
check("log 🔒 khi giữ proxy ngay", "🔒 Giữ proxy 1.1.1.1" in log, log[:200])
check("log ⏳ khi phải chờ", "⏳ Chờ proxy 1.1.1.1 đang được A1" in log)
check("đang chờ được đánh dấu cho thanh trạng thái", waiting_now == {"A2": "1.1.1.1"}, str(waiting_now))
check("log 🔓 khi nhả + số profile đang chờ", "🔓 Nhả proxy 1.1.1.1 — 1 profile đang chờ IP này." in log)
check("log ✅ khi tới lượt (kèm thời gian chờ)", "✅ Proxy 1.1.1.1 đã rảnh — tới lượt chạy" in log)
check("tới lượt -> bỏ khỏi danh sách chờ", ui._PROXY_WAITING == {})
check("profile không proxy cũng có log", "Không có proxy — không cần chặn trùng" in log)

print("\n== 3. Thanh trạng thái + hộp xác nhận (GUI thật)")
root = tk.Tk()
root.withdraw()
app = ui.AutomationApp(root)
sys.stdout = sys.__stdout__
root.update()
app._running = True
app._active_slots = [0]
ui._PROXY_WAITING.clear()
ui._PROXY_WAITING.update({"X": "1.1.1.1", "Y": "2.2.2.2"})
ui._PROXY_STATE.update(on=True, why="", n_proxy=31)
app._tick_status()
root.update()
st = app.var_status.get()
check("đang chạy -> luôn có 'Chặn trùng proxy: BẬT'", "Chặn trùng proxy: BẬT (31 proxy)" in st, st)
check("số profile đang chờ proxy", "2 profile chờ proxy rảnh" in st, st)
ui._PROXY_WAITING.clear()
app._tick_status()
root.update()
check("không ai chờ -> nói rõ", "không ai phải chờ" in app.var_status.get(), app.var_status.get())
ui._PROXY_STATE.update(on=False, why="BitBrowser chưa hỗ trợ đọc proxy")
app._tick_status()
root.update()
check("TẮT -> vẫn hiện kèm lý do", "Chặn trùng proxy: TẮT (BitBrowser" in app.var_status.get())
app._running = False

app._proxy_note = ui.proxy_summary_lines(list(PM), PM, 4)
seen = {}


def _peek():
    for w in root.winfo_children():
        if isinstance(w, tk.Toplevel) and "Xác nhận" in str(w.title()):
            texts = []

            def walk(x):
                for c in x.winfo_children():
                    try:
                        texts.append(str(c.cget("text")))
                    except Exception:
                        pass
                    walk(c)
            walk(w)
            seen["t"] = "\n".join(texts)
            for c in w.winfo_children():
                for b in c.winfo_children():
                    if isinstance(b, ttk.Button) and str(b.cget("text")) == "HỦY":
                        b.invoke()
                        return
    root.after(100, _peek)


root.after(200, _peek)
ok = app.show_assignment_confirm([{"pid": "A1", "google": "x", "yt": "x", "round": 1}])
t = seen.get("t", "")
check("hộp xác nhận có dòng chặn trùng proxy", "Chặn trùng proxy: BẬT" in t, t[:200])
check("hộp xác nhận liệt kê proxy dùng chung", "1.1.1.1: 3 profile" in t)
check("bấm HỦY vẫn hoạt động", ok is False)
root.destroy()

print("\n== 4. Tĩnh")
src = open(os.path.join(SRC, "ui_main.py"), encoding="utf-8").read()
check("start_automation đọc proxy TRƯỚC hộp xác nhận",
      src.index("self._proxy_prefetch = (browser_type, _pmap, _why)") <
      src.index("if not self.show_assignment_confirm(assign_rows, pinned=pinned_flag):"))
check("run_thread_pool dùng lại map đã đọc + luôn in tóm tắt",
      'getattr(self, "_proxy_prefetch", None)' in src and "for _ln in proxy_summary_lines(" in src)

print(f"\nPASS: {PASS}   FAIL: {FAIL}")
print("SMOKE v1.8.2: ALL PASS" if FAIL == 0 else "SMOKE v1.8.2: CO LOI")
sys.exit(0 if FAIL == 0 else 1)
