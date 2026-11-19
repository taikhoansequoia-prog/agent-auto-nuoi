# -*- coding: utf-8 -*-
"""Smoke test v1.7.7 — MỖI PROFILE DÙNG TRỌN CỤM TỪ KHÓA (xoay vòng nối tiếp phiên sau).

Bối cảnh: user nhập 1 từ khóa gốc -> Sinh ra 5 -> Áp dụng -> khi chạy mỗi profile chỉ
nhận ĐÚNG 1 trong 5 (round-robin), phiên lại nhờ AI viết kế hoạch mới -> 4 từ khóa còn lại
không bao giờ dùng. v1.7.7:
  - Áp dụng giữ nhóm: mỗi dòng gốc = 1 CỤM trong danh sách (ngăn bằng dòng trống)
  - Chạy: mỗi profile nhận TRỌN 1 cụm, dùng NGUYÊN VĂN lần lượt, không gọi AI
  - Thứ tự nối tiếp phiên sau: từ khóa chưa dùng đứng đầu (bảng keyword_usage)

Chạy OFFLINE: python src\\test_v177.py  (DB/.env ở thư mục tạm; hash .env/DB thật đối chiếu)
"""
import hashlib
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

TMP = tempfile.mkdtemp(prefix="gpm_v177_")
os.environ["GPM_BOT_DATA_DIR"] = TMP
os.environ["GPM_BOT_ENV_FILE"] = os.path.join(TMP, ".env")

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


def sha(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:12]
    except Exception:
        return "(none)"


REAL_ENV = os.path.join(ROOT, ".env")
REAL_DB = os.path.join(ROOT, "data", "agent_logs.db")
H_ENV, H_DB = sha(REAL_ENV), sha(REAL_DB)

import tkinter as tk  # noqa: E402
import src.ui_main as ui  # noqa: E402
from src import app_config  # noqa: E402
from src.database.db_handler import DatabaseHandler  # noqa: E402
from src.workflow.warmup import WarmupWorkflow  # noqa: E402

A = [f"walking kw{i}" for i in range(1, 6)]
B = [f"camping kw{i}" for i in range(1, 6)]

print("\n== 1. DB keyword_usage")
db = DatabaseHandler()
check("DB nằm ở thư mục tạm", db.db_path.startswith(TMP), db.db_path)
check("log_keyword_used ghi", db.log_keyword_used("P1", "Walking KW1"))
db.log_keyword_used("P1", "walking kw2")
db.log_keyword_used("P2", "walking kw3")
lu = db.get_keyword_last_used("P1", A)
check("get_keyword_last_used đúng 2 từ khóa của P1 (lowercase)", set(lu) == {"walking kw1", "walking kw2"}, str(lu))
check("không lẫn profile khác", "walking kw3" not in lu)
check("pid rỗng -> {}", db.get_keyword_last_used("", A) == {})
check("keyword rỗng -> False", db.log_keyword_used("P1", "  ") is False)

print("\n== 2. order_cluster_for_profile (nối tiếp phiên sau)")
cl = [{"google_query": k, "youtube_query": k} for k in A]
o = ui.order_cluster_for_profile(cl, lu, rng=random.Random(1))
names = [c["google_query"] for c in o]
check("giữ đủ 5 từ khóa", sorted(names) == sorted(A), str(names))
check("3 từ khóa CHƯA dùng đứng đầu", set(names[:3]) == {"walking kw3", "walking kw4", "walking kw5"}, str(names))
lu2 = {"walking kw1": "2026-11-01T10:00:00", "walking kw2": "2026-11-01T09:00:00",
       "walking kw3": "2026-11-01T11:00:00", "walking kw4": "2026-11-01T08:00:00",
       "walking kw5": "2026-11-01T12:00:00"}
names2 = [c["google_query"] for c in ui.order_cluster_for_profile(cl, lu2)]
check("dùng hết -> CŨ NHẤT trước", names2 == ["walking kw4", "walking kw2", "walking kw1",
                                              "walking kw3", "walking kw5"], str(names2))
orders = {tuple(c["google_query"] for c in ui.order_cluster_for_profile(cl, {}, rng=random.Random(s)))
          for s in range(6)}
check("chưa dùng gì -> các profile có thứ tự KHÁC nhau", len(orders) > 1, str(len(orders)))

print("\n== 3. clusters_to_themes + assign_topics_for_run")
clusters = [[{"google_query": k, "youtube_query": k + " yt"} for k in A],
            [{"google_query": k, "youtube_query": k} for k in B]]
themes = ui.clusters_to_themes(clusters)
check("2 cụm -> 2 theme", len(themes) == 2)
check("theme mang trọn cụm", len(themes[0]["cluster"]) == 5)
amap, rows = ui.assign_topics_for_run(["p1", "p2", "p3"], themes)
check("mỗi profile nhận TRỌN 1 cụm 5 từ khóa", all(len(amap[p]["cluster"]) == 5 for p in amap))
check("2 cụm đều được dùng (3 profile)",
      {amap[p]["cluster"][0]["google_query"] for p in amap} == {A[0], B[0]})
check("bảng phân bổ ghi '(5 từ khóa)'", all("(5 từ khóa)" in r["google"] for r in rows), rows[0]["google"])
check("rows có cluster_size", all(r.get("cluster_size") == 5 for r in rows))
amap1, _ = ui.assign_topics_for_run(["p1"], ui.clusters_to_themes(
    [[{"google_query": "solo", "youtube_query": "solo"}]]))
check("cụm 1 từ khóa -> hiển thị như cũ", _[0]["google"] == "solo")

print("\n== 4. GUI: Áp dụng giữ nhóm cụm + lưu/khôi phục")
root = tk.Tk()
root.withdraw()
app = ui.AutomationApp(root)
sys.stdout = sys.__stdout__
root.update()
topics = ([{"google_query": k, "youtube_query": k, "seed": "walking"} for k in A]
          + [{"google_query": k, "youtube_query": k + " vlog", "seed": "camping"} for k in B])
app._show_generated_topics_preview("walking / camping", topics)
root.update()
pv = None
for w in root.winfo_children():
    if isinstance(w, tk.Toplevel):
        for b in w.winfo_children():
            pass
        pv = w
from tkinter import ttk  # noqa: E402


def find_btn(w, text):
    for c in w.winfo_children():
        if isinstance(c, (ttk.Button, tk.Button)) and str(c.cget("text")) == text:
            return c
        r = find_btn(c, text)
        if r:
            return r
    return None


btn = find_btn(pv, "Áp dụng") if pv else None
check("bảng xem trước có nút Áp dụng", btn is not None)
if btn:
    btn.invoke()
    root.update()
raw = app.kw_text.get("1.0", "end-1c")
check("danh sách có 2 khối ngăn bằng 1 dòng trống", "\n\n" in raw and raw.count("\n\n") == 1, repr(raw[:120]))
cls = app._collect_kw_clusters()
check("_collect_kw_clusters = 2 cụm × 5", [len(c) for c in cls] == [5, 5], str([len(c) for c in cls]))
check("YouTube tách riêng giữ nguyên", cls[1][0]["youtube_query"] == B[0] + " vlog", cls[1][0]["youtube_query"])
check("_collect_kw_pairs vẫn phẳng 10", len(app._collect_kw_pairs()) == 10)
app.save_current_config()
cfg = app_config.load_config()
check("config lưu vạch ngăn ''", "" in cfg.get("kw_google", []), str(cfg.get("kw_google")))
app.kw_text.delete("1.0", "end")
app._rebuild_kw_rows(cfg["kw_google"], cfg["kw_youtube"])
check("khôi phục từ config đúng 2 cụm", [len(c) for c in app._collect_kw_clusters()] == [5, 5])
app._rebuild_kw_rows(["a", "b", "c"], ["", "", ""])
check("danh sách không dòng trống = 1 cụm (mọi profile dùng hết)",
      [len(c) for c in app._collect_kw_clusters()] == [3])
app._rebuild_kw_rows(["", "a", "", "", "b", ""], [])
check("vạch ngăn thừa ở đầu/cuối/trùng được gộp", app.kw_text.get("1.0", "end-1c") == "a\n\nb",
      repr(app.kw_text.get("1.0", "end-1c")))
root.destroy()

print("\n== 5. run_single_profile -> workflow nhận cụm đã sắp thứ tự")


class FakeWorkflow:
    made = []

    def __init__(self, *a, **k):
        self.kw = k
        self.session_deadline_s = 0
        self.keyword_cluster = []
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
    db.log_keyword_used("PX", A[0])
    db.log_keyword_used("PX", A[1])
    try:
        ui.run_single_profile(FakeAPI(), "PX", "Profile PX", [], 0, 1200, 800, False, False,
                              assigned_theme=themes[0])
    except Exception:
        pass
    wf = FakeWorkflow.made[-1] if FakeWorkflow.made else None
    got = [c["google_query"] for c in (wf.keyword_cluster if wf else [])]
    check("workflow nhận trọn cụm 5", len(got) == 5, str(got))
    check("2 từ khóa đã dùng phiên trước bị dời xuống cuối", set(got[-2:]) == {A[0], A[1]}, str(got))
    check("session_theme = từ khóa đầu cụm", wf and wf.kw["session_theme"]["google_query"] == got[0])
    try:
        ui.run_single_profile(FakeAPI(), "PY", "Profile PY", [{"google_query": "x", "youtube_query": "x"}],
                              0, 1200, 800, False, False,
                              assigned_theme={"google_query": "solo", "youtube_query": "solo"})
    except Exception:
        pass
    check("không có cụm -> keyword_cluster rỗng (hành vi cũ)", FakeWorkflow.made[-1].keyword_cluster == [])
finally:
    ui.WarmupWorkflow, ui.BrowserController, ui.adjust_window_bounds, ui.time.sleep = real

print("\n== 6. WarmupWorkflow dùng nguyên văn cụm, không gọi AI")


class FakeContext:
    def on(self, *a, **k):
        return None

    def new_page(self):
        return None


class CountBrain:
    calls = 0

    def ask_text(self, *_a, **_k):
        CountBrain.calls += 1
        return "- google | ai invented keyword"


wf = WarmupWorkflow(context=FakeContext(), db_handler=db, profile_id="PW", brain=CountBrain())
wf.keyword_cluster = [{"google_query": k, "youtube_query": k + " yt"} for k in A[:3]]
seq = [wf._plan_keyword("google", "google_query", "d"),
       wf._plan_keyword("youtube", "youtube_query", "d"),
       wf._plan_keyword("maps", "google_query", "d"),
       wf._plan_keyword("news", "google_query", "d")]
check("lần lượt theo cụm", seq[0] == A[0] and seq[2] == A[2], str(seq))
check("action YouTube lấy youtube_query", seq[1] == A[1] + " yt", seq[1])
check("hết cụm -> quay lại đầu", seq[3] == A[0], seq[3])
check("không gọi AI", CountBrain.calls == 0, str(CountBrain.calls))
check("ghi keyword_usage cho phiên sau", set(db.get_keyword_last_used("PW")) == set(A[:3]),
      str(db.get_keyword_last_used("PW")))
wf2 = WarmupWorkflow(context=FakeContext(), db_handler=None, profile_id=None)
check("không cụm -> _plan_keyword như cũ (session_theme)",
      wf2._plan_keyword("google", "google_query", "d") == wf2.session_theme.get("google_query"))
src_w = open(os.path.join(SRC, "workflow", "warmup.py"), encoding="utf-8").read()
check("run_random_session bỏ qua kế hoạch AI khi có cụm",
      "if self.keyword_cluster:" in src_w and "elif self.brain:\n            plan = self._safe_ask_plan" in src_w.replace("\r\n", "\n"))

print("\n== 7. Tĩnh + dữ liệu thật")
src_u = open(os.path.join(SRC, "ui_main.py"), encoding="utf-8").read()
# v1.8.3: user đổi ý — mỗi profile 1 chủ đề RIÊNG (cụm chỉ làm gợi ý cho AI), không còn dùng chung 1 cụm
check("start_automation: v1.8.3 mỗi dòng 1 chủ đề (cụm làm gợi ý)",
      "_themes_now = lines_to_themes(self._collect_kw_clusters())" in src_u)
check(".env thật không đổi", sha(REAL_ENV) == H_ENV)
check("DB thật không đổi", sha(REAL_DB) == H_DB)

print(f"\nPASS: {PASS}   FAIL: {FAIL}")
print("SMOKE v1.7.7: ALL PASS" if FAIL == 0 else "SMOKE v1.7.7: CO LOI")
sys.exit(0 if FAIL == 0 else 1)
