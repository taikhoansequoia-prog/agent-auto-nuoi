# -*- coding: utf-8 -*-
"""Smoke test v1.8.4 — XEM TRƯỚC KẾ HOẠCH TỪ KHÓA TỪNG PROFILE + PHIÊN DÙNG ĐÚNG KẾ HOẠCH ĐÓ.

User: "sao không thấy các từ khóa khác được sinh ra trong 1 phiên, chỉ có 1 cụm" — trước đây
kế hoạch 8-14 bước chỉ sinh SAU khi phiên mở trình duyệt. v1.8.4: sinh trong nền ngay khi
hộp xác nhận mở, hiện cột "Kế hoạch (AI)" + khung chi tiết; bấm CHẠY -> phiên dùng đúng nó.

Chạy OFFLINE: python src\\test_v184.py
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
os.environ["GPM_BOT_DATA_DIR"] = tempfile.mkdtemp(prefix="gpm_v184_")
os.environ["GPM_BOT_ENV_FILE"] = os.path.join(os.environ["GPM_BOT_DATA_DIR"], ".env")

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


print("\n== 1. build_session_plan / plan_summary")
plan, src = ui.build_session_plan("home workout", ["yoga mat near me", "how to do pushups"], "none", "en")
check("không AI -> kế hoạch dự phòng", src == "dự phòng" and len(plan) >= 6, f"{src} {len(plan)}")
check("dự phòng dùng từ khóa liên quan", any(s["query"] == "yoga mat near me" and s["platform"] == "maps" for s in plan))


class FakeBrain:
    def ask_text(self, p):
        return "google | home workout plan\nyoutube | 20 min home workout\ngoogle | buy yoga mat\nmaps | gym near me\nnews | fitness trends 2026"


real_gb = ui.BrainManager.get_brain
ui.BrainManager.get_brain = staticmethod(lambda bt: FakeBrain())
try:
    plan2, src2 = ui.build_session_plan("home workout", [], "gemini", "en")
finally:
    ui.BrainManager.get_brain = real_gb
check("có AI -> kế hoạch của AI", src2 == "AI" and plan2[1]["query"] == "20 min home workout", src2)
check("tóm tắt cột", ui.plan_summary(plan2) == "5 bước · google → youtube → google → maps …", ui.plan_summary(plan2))

print("\n== 2. _prepare_plans (thread nền) ghi kế hoạch cho từng profile")
real_rb = ui.resolve_run_brain
ui.resolve_run_brain = lambda bt, log=print: "none"
out = {}
amap = {"P1": {"google_query": "home workout", "youtube_query": "x", "related": []},
        "P2": {"google_query": "budget travel", "youtube_query": "x", "related": ["cheap flights"]}}
stub = type("S", (), {})()
ui.AutomationApp._prepare_plans(stub, amap, "claude-sonnet", "en", out)
ui.resolve_run_brain = real_rb
check("mỗi profile có kế hoạch riêng", set(out) == {"P1", "P2"} and out["P1"]["plan"] != out["P2"]["plan"])
check("ghi lại AI đã dò để chạy dùng luôn", stub._plan_brain == "none")

print("\n== 3. Hộp xác nhận hiện kế hoạch (GUI thật)")
root = tk.Tk()
root.withdraw()
app = ui.AutomationApp(root)
sys.stdout = sys.__stdout__
root.update()
app._proxy_note = []
app._plan_preview = {"P1": {"plan": plan2, "src": "AI"}}   # P2 vẫn "đang sinh"
rows = [{"pid": "P1", "google": "home workout", "yt": "x", "round": 1},
        {"pid": "P2", "google": "budget travel", "yt": "x", "round": 1}]
seen = {}


def find(w, cls):
    out_ = []
    for c in w.winfo_children():
        if isinstance(c, cls):
            out_.append(c)
        out_ += find(c, cls)
    return out_


def _peek(step=[0]):
    for w in root.winfo_children():
        if isinstance(w, tk.Toplevel) and "Xác nhận" in str(w.title()):
            step[0] += 1
            if step[0] == 4:   # đợi poll chạy vài vòng
                tree = find(w, ttk.Treeview)[0]
                seen["plan_col"] = [tree.set(i, "plan") for i in tree.get_children()]
                seen["detail"] = find(w, tk.Text)[0].get("1.0", "end")
                app._plan_preview["P2"] = {"plan": plan, "src": "dự phòng"}   # P2 xong sau
            if step[0] == 8:
                tree = find(w, ttk.Treeview)[0]
                seen["plan_col2"] = [tree.set(i, "plan") for i in tree.get_children()]
                for b in find(w, ttk.Button):
                    if str(b.cget("text")) == "HỦY":
                        b.invoke()
                        return
    root.after(400, _peek)


root.after(300, _peek)
ok = app.show_assignment_confirm(rows)
check("cột Kế hoạch: P1 có tóm tắt, P2 'đang sinh…'",
      seen.get("plan_col", ["", ""])[0].startswith("5 bước") and seen["plan_col"][1] == "đang sinh…",
      str(seen.get("plan_col")))
check("khung chi tiết liệt kê đủ bước của profile đang chọn",
      "1. [google] home workout plan" in seen.get("detail", "") and "4. [maps] gym near me" in seen.get("detail", ""),
      seen.get("detail", "")[:120])
check("P2 xong sau -> cột tự cập nhật", (seen.get("plan_col2") or ["", ""])[1].endswith("bước · google → " +
      " → ".join(s["platform"] for s in plan[1:4]) + " …") or "bước" in (seen.get("plan_col2") or ["", ""])[1],
      str(seen.get("plan_col2")))
check("HỦY vẫn hoạt động", ok is False)
root.destroy()

print("\n== 4. Phiên dùng đúng kế hoạch đã duyệt")


class FakeWorkflow:
    made = []

    def __init__(self, *a, **k):
        self.kw = k
        self.session_deadline_s = 0
        self.keyword_cluster = []
        self.plan_steps = []
        self.related_keywords = []
        FakeWorkflow.made.append(self)

    def run_random_session(self, total_actions=0):
        raise RuntimeError("STUB")


class FakeController:
    def __init__(self, ws):
        class _B:
            contexts = [object()]
        self.browser = _B()

    def connect(self):
        return True

    def close(self):
        pass


class FakeAPI:
    def open_profile(self, pid):
        return "ws://stub"

    def close_profile(self, pid):
        pass


real = (ui.WarmupWorkflow, ui.BrowserController, ui.adjust_window_bounds, ui.time.sleep)
ui.WarmupWorkflow, ui.BrowserController = FakeWorkflow, FakeController
ui.adjust_window_bounds = lambda *a, **k: None
ui.time.sleep = lambda *a, **k: None
ui.STOP_EVENT.clear()
try:
    try:
        ui.run_single_profile(FakeAPI(), "PX", "Profile PX", [], 0, 1200, 800, False, False,
                              assigned_theme={"google_query": "home workout", "youtube_query": "x",
                                              "related": [], "plan": plan2})
    except Exception:
        pass
    wf = FakeWorkflow.made[-1]
    check("workflow nhận đúng kế hoạch đã duyệt", wf.plan_steps == plan2, str(len(wf.plan_steps)))
finally:
    ui.WarmupWorkflow, ui.BrowserController, ui.adjust_window_bounds, ui.time.sleep = real

src_w = open(os.path.join(SRC, "workflow", "warmup.py"), encoding="utf-8").read()
check("warmup: có kế hoạch sẵn -> không hỏi AI lại",
      "preset_plan = bool(self.plan_steps)" in src_w and "if self.keyword_cluster or preset_plan:" in src_w)
src_u = open(os.path.join(SRC, "ui_main.py"), encoding="utf-8").read()
check("start_automation sinh kế hoạch TRƯỚC hộp xác nhận",
      src_u.index("target=self._prepare_plans") < src_u.index("if not self.show_assignment_confirm(assign_rows, pinned=pinned_flag):"))
check("gắn kế hoạch bằng BẢN SAO dict (không dùng chung giữa 2 profile)",
      "assignment_map[_pid] = dict(assignment_map[_pid], plan=list(_pv[\"plan\"]))" in src_u)

print(f"\nPASS: {PASS}   FAIL: {FAIL}")
print("SMOKE v1.8.4: ALL PASS" if FAIL == 0 else "SMOKE v1.8.4: CO LOI")
sys.exit(0 if FAIL == 0 else 1)
