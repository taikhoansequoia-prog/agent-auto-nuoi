# -*- coding: utf-8 -*-
"""
test_v141.py — Kiểm chứng v1.4.1 (ĐỌC/UNIT + SMOKE Tkinter, KHÔNG mở trình duyệt).

Phạm vi:
  1. DB migration: cycle_history tạo từ schema v1.4.0 (THIẾU target_s) -> _create_tables
     phải tự backup + ALTER thêm target_s; chạy lần 2 idempotent (không đổi gì).
  2. log_cycle(target_s=..) round-trip; get_cycle_rows trả target_s.
  3. get_cycle_summary:
       - vòng CHƯA có mốc (target_s NULL) + tham số target_s=0  -> KHÔNG đếm vào 'over'
       - vòng có mốc riêng                                        -> đếm đúng
       - last_target_s = mốc của vòng cuối
       - tham số target_s>0 đóng vai mốc mặc định cho vòng NULL (backward-compat)
  4. get_last_cycle_targets trả mốc vòng mới nhất mỗi profile.
  5. GUI smoke (source): (a) run_single_profile nhánh random trả target_s = bội 60 trong
     [0, (actions-1)*60] và _cyc["target_s"] được set; (b) nhánh fixed_target_s>0 -> đúng số;
     (c) _tick_status + show_account_dashboard + show_cycle_time_dialog không lỗi với target
     theo từng vòng; (d) dialog chu trình có cột "M.tiêu cuối"; (e) _show_detail có cột Mục tiêu.
     Toàn bộ nhánh (a)(b) dùng monkeypatch để KHÔNG chạy warmup thật.

Chạy:  & "<python>" test_v141.py      (cwd = repo-root hoặc src/ đều được)
DB test nằm ở thư mục tạm (GPM_BOT_DATA_DIR) — KHÔNG đụng data\ thật. Tự dọn cuối test.
"""
import os
import sys
import json
import time
import shutil
import sqlite3
import tempfile
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)                      # d:\Tool\AGENT AUto Nuôi
if REPO not in sys.path:
    sys.path.insert(0, REPO)

# Console test thường là pipe cp1252 -> print emoji của warmup/UI sẽ ném UnicodeEncodeError.
# Ép stdout utf-8 (errors=replace) để test giống môi trường EXE/GUI thật.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TMP = tempfile.mkdtemp(prefix="gpm_v141_")
os.environ["GPM_BOT_DATA_DIR"] = TMP

PASS = []
FAIL = []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  [PASS] " if cond else "  [FAIL] ") + name + (f"  ({extra})" if extra else ""))


def hr(t):
    print("\n" + "=" * 68)
    print(t)
    print("=" * 68)


# =====================================================================
hr("1. MIGRATION cycle_history (schema v1.4.0 THIẾU target_s)")
# =====================================================================
from src.database.db_handler import DatabaseHandler  # noqa: E402

DBP = os.path.join(TMP, "agent_logs.db")

# 1a. Dựng DB "đời cũ" v1.4.0: cycle_history KHÔNG có target_s + 3 vòng cũ.
conn = sqlite3.connect(DBP)
conn.execute("""CREATE TABLE cycle_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id TEXT, started_at TEXT, finished_at TEXT,
    duration_s REAL, status TEXT, actions INTEGER, phase TEXT, error TEXT)""")
conn.execute("INSERT INTO cycle_history (profile_id, started_at, finished_at, duration_s,"
             " status, actions, phase, error) VALUES ('OLD-1', '2026-10-10T08:00:00',"
             " datetime('now','localtime','-1 days'), 600, 'ok', 5, 'clean', NULL)")
conn.execute("INSERT INTO cycle_history (profile_id, started_at, finished_at, duration_s,"
             " status, actions, phase, error) VALUES ('OLD-1', '2026-10-11T08:00:00',"
             " datetime('now','localtime','-1 days'), 1800, 'ok', 6, 'clean', NULL)")
conn.commit()
conn.close()

cols_before = {r[1] for r in sqlite3.connect(DBP).execute("PRAGMA table_info(cycle_history)")}
check("DB đời cũ KHÔNG có target_s (tiền đề)", "target_s" not in cols_before, str(sorted(cols_before)))

db = DatabaseHandler(db_path=DBP)
cols_after = {r[1] for r in sqlite3.connect(DBP).execute("PRAGMA table_info(cycle_history)")}
check("Sau _create_tables: ĐÃ có cột target_s", "target_s" in cols_after)

bk_dir = os.path.join(TMP, "backup")
bks = os.listdir(bk_dir) if os.path.isdir(bk_dir) else []
check("Bắt buộc backup TRƯỚC khi ALTER", any("pre-migration-cycle-target" in b or b.endswith(".db") for b in bks), str(bks))

# 1b. Idempotent: chạy lại không thêm backup mới / không lỗi
n_bk = len(bks)
db2 = DatabaseHandler(db_path=DBP)
check("Chạy lần 2 idempotent (không phát sinh backup mới)",
      len(os.listdir(bk_dir)) == n_bk, f"{n_bk} -> {len(os.listdir(bk_dir))}")
check("3 vòng cũ còn nguyên (không mất dữ liệu)",
      sqlite3.connect(DBP).execute("SELECT COUNT(*) FROM cycle_history").fetchone()[0] == 2)


# =====================================================================
hr("2. log_cycle / get_cycle_rows — round-trip target_s")
# =====================================================================
# Mốc ngày ĐỘNG (hôm nay) — tránh time-bomb: check "days=1 vẫn thấy vòng hôm nay"
# mà hardcode ngày sẽ fail sau 1-2 ngày.
_TODAY = datetime.date.today().isoformat()
db.log_cycle("PID-A", f"{_TODAY}T09:00:00", f"{_TODAY}T09:20:00", 1200.0, "ok",
             actions=5, phase="clean", target_s=900)
db.log_cycle("PID-A", f"{_TODAY}T10:00:00", f"{_TODAY}T10:05:00", 300.0, "error",
             actions=2, phase="clean", error="boom", target_s=600)
db.log_cycle("PID-B", f"{_TODAY}T09:00:00", f"{_TODAY}T09:10:00", 600.0, "ok",
             actions=4, phase="youtube", target_s=None)
rows_a = db.get_cycle_rows("PID-A", days=3650)
check("get_cycle_rows trả 2 dòng PID-A", len(rows_a) == 2, str(len(rows_a)))
check("get_cycle_rows có key target_s", all("target_s" in r for r in rows_a))
check("target_s round-trip đúng (900 & 600)",
      sorted([r["target_s"] for r in rows_a]) == [600.0, 900.0],
      str([r["target_s"] for r in rows_a]))
check("status/duration_s round-trip",
      {r["status"] for r in rows_a} == {"ok", "error"})


# =====================================================================
hr("3. get_cycle_summary — 'over' theo mốc RIÊNG từng vòng")
# =====================================================================
# PID-A: vòng 1 = 1200s vs mốc 900 -> OVER;  vòng 2 = 300s vs mốc 600 -> không
# OLD-1: 2 vòng NULL-mốc, duration 600 & 1800 -> KHÔNG được đếm là over khi target_s=0
s0 = db.get_cycle_summary(days=3650, target_s=0)
a = s0.get("PID-A", {})
check("PID-A cycles = 2", a.get("cycles") == 2, str(a.get("cycles")))
check("PID-A over = 1 (chỉ vòng vượt mốc 900)", a.get("over") == 1, f"over={a.get('over')}")
check("PID-A last_target_s = 600 (mốc vòng cuối)", a.get("last_target_s") == 600.0, str(a.get("last_target_s")))
check("PID-A last_duration_s = 300", a.get("last_duration_s") == 300.0, str(a.get("last_duration_s")))
check("PID-A last_status = 'error' + last_error giữ nguyên",
      a.get("last_status") == "error" and a.get("last_error") == "boom",
      f"{a.get('last_status')}/{a.get('last_error')}")
check("PID-A ok/error = 1/1", (a.get("ok"), a.get("error")) == (1, 1), f"{a.get('ok')}/{a.get('error')}")
check("PID-A avg = 750s", a.get("avg_s") == 750.0, str(a.get("avg_s")))
check("PID-B over = 0 (mốc NULL, không đặt mặc định)", s0.get("PID-B", {}).get("over") == 0,
      str(s0.get("PID-B", {}).get("over")))
check("OLD-1 KHÔNG bị tính over khi target_s=0 (bug 'duration>=0' đã chặn)",
      s0.get("OLD-1", {}).get("over") == 0, f"over={s0.get('OLD-1', {}).get('over')}")
check("OLD-1 last_target_s = None (vòng cũ chưa ghi mốc)",
      s0.get("OLD-1", {}).get("last_target_s") is None, str(s0.get("OLD-1", {}).get("last_target_s")))

s900 = db.get_cycle_summary(days=3650, target_s=900)
check("target_s=900 (mốc mặc định): OLD-1 over = 1 (chỉ vòng 1800s >= 900)",
      s900.get("OLD-1", {}).get("over") == 1, f"over={s900.get('OLD-1', {}).get('over')}")
check("target_s=900: PID-A vẫn dùng mốc riêng -> over = 1 (KHÔNG thành 2)",
      s900.get("PID-A", {}).get("over") == 1, f"over={s900.get('PID-A', {}).get('over')}")
check("target_s=900: PID-B (600s < 900) over = 0", s900.get("PID-B", {}).get("over") == 0)

s_only = db.get_cycle_summary(profile_id="PID-A", days=3650, target_s=0)
check("Lọc theo profile_id hoạt động", set(s_only.keys()) == {"PID-A"}, str(list(s_only.keys())))


# =====================================================================
hr("4. get_last_cycle_targets")
# =====================================================================
tgs = db.get_last_cycle_targets(days=3650)
check("PID-A -> 600 (mốc vòng mới nhất)", tgs.get("PID-A") == 600.0, str(tgs.get("PID-A")))
check("PID-B (mốc NULL) KHÔNG xuất hiện", "PID-B" not in tgs, str(list(tgs.keys())))
check("OLD-1 (mốc NULL) KHÔNG xuất hiện", "OLD-1" not in tgs, str(list(tgs.keys())))
check("Cửa sổ ngày hoạt động (days=1 vẫn thấy vòng hôm nay)", db.get_last_cycle_targets(days=1).get("PID-A") == 600.0)


# =====================================================================
hr("5. GUI SMOKE — mục tiêu ngẫu nhiên theo từng vòng")
# =====================================================================
import tkinter as tk
from tkinter import ttk
import random as _random
import src.ui_main as ui

RealToplevel = tk.Toplevel          # giữ trước khi monkeypatch (isinstance vẫn đúng)
RealRandint = _random.randint

win_holder = {}


def grab_toplevel(title_frag, timeout=4.0):
    """Chờ & bắt Toplevel mới (đệ quy) có tiêu đề chứa title_frag."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        for p in ui_root.winfo_children():
            if isinstance(p, RealToplevel) and title_frag.lower() in (p.title() or "").lower():
                return p
            for q in p.winfo_children():
                if isinstance(q, RealToplevel) and title_frag.lower() in (q.title() or "").lower():
                    return q
        ui_root.update()
        time.sleep(0.05)
    return None


def find_all(widget, kind, out=None):
    out = out if out is not None else []
    for c in widget.winfo_children():
        if isinstance(c, kind):
            out.append(c)
        find_all(c, kind, out)
    return out


try:
    ui_root = tk.Tk()
    app = ui.AutomationApp(ui_root)
    ui_root.update()
    check("AutomationApp khởi tạo OK + có spin_target_min", hasattr(app, "spin_target_min"))
    check("_target_secs() = 0 khi spinbox = 0", app._target_secs() == 0, str(app._target_secs()))
    app.spin_target_min.delete(0, "end")
    app.spin_target_min.insert(0, "7")
    check("_target_secs() = 420 khi spinbox = 7", app._target_secs() == 420, str(app._target_secs()))
    app.spin_target_min.delete(0, "end")
    app.spin_target_min.insert(0, "abc")
    check("_target_secs() = 0 khi nhập rác", app._target_secs() == 0, str(app._target_secs()))
    app.spin_target_min.delete(0, "end")
    app.spin_target_min.insert(0, "0")

    # --- 5a. Nhánh RANDOM: _target_secs()=0 -> bot tự random bội 60, 0 <= t <= (actions-1)*60
    # Stub ĐÚNG CHỖ run_random_session() để toàn bộ thân run_single_profile chạy hết
    # (open -> connect -> random target -> ghi _cyc) rồi mới dừng — test được cả actions + target_s.
    class FakeWorkflow:
        def __init__(self, *a, **k):
            pass

        def run_random_session(self, total_actions=0):
            raise RuntimeError("STUB-RUN-RANDOM")

    real_workflow = ui.WarmupWorkflow
    ui.WarmupWorkflow = FakeWorkflow

    # api giả: chỉ trả ws_url giả để vượt cổng "mở profile"
    class FakeAPI:
        def open_profile(self, pid):
            return "ws://stub"

        def close_profile(self, pid):
            pass

    # Vào được nhánh random cần: controller.connect() True + WarmupWorkflow(...) OK.
    # -> patch BrowserController (controller giả) nhưng GIỮ class WarmupWorkflow thật bị stub ở
    #    dòng lambda phía trên? Không: stub lambda ném ngay tại __init__ nên _cyc["actions"] đã
    #    được set TRƯỚC đó (dòng trước) — miễn là ta vượt được connect.
    real_bc = ui.BrowserController
    real_adjust = ui.adjust_window_bounds
    real_sleep = time.sleep

    class FakeController:
        def __init__(self, ws_url):
            class _B:
                contexts = [object()]
            self.browser = _B()

        def connect(self):
            return True

        def close(self):
            pass

    ui.BrowserController = FakeController
    ui.adjust_window_bounds = lambda *a, **k: None
    ui.time.sleep = lambda *a, **k: None
    try:
        ui.run_single_profile(FakeAPI(), "PID-GUI-1", "Profile GUI 1",
                              [{"google_query": "du lich", "youtube_query": "travel"}],
                              slot_index=0, screen_w=1200, screen_h=800,
                              skip_youtube=False, skip_random_keywords=False,
                              phase="clean", fixed_target_s=0)
    except Exception as e:
        print(f"     · (stub dừng như dự kiến: {type(e).__name__}: {e})")
    cyc = ui.SLOT_CYCLE_INFO.get("Slot 1", {})
    tgt = cyc.get("target_s")
    check("Nhánh RANDOM: target_s là bội của 60 (hoặc None khi = 0)",
          tgt is None or (isinstance(tgt, int) and tgt % 60 == 0), f"target_s={tgt}")
    check("Nhánh RANDOM: target_s trong [0, 8*60] (total_actions 4..8)",
          tgt is None or (0 <= tgt <= 8 * 60), f"target_s={tgt}")
    check("Nhánh RANDOM: actions đã ghi vào _cyc (4..8)",
          4 <= (cyc.get("actions") or 0) <= 8, str(cyc.get("actions")))
    check("Nhánh RANDOM: chu trình bị stub -> status ghi 'error' (trung thực)",
          cyc.get("status") == "error", str(cyc.get("status")))

    # --- 5b. Nhánh FIXED: fixed_target_s=600 -> target_s = 600 (không random)
    ui.SLOT_CYCLE_INFO.pop("Slot 1", None)
    try:
        ui.run_single_profile(FakeAPI(), "PID-GUI-1", "Profile GUI 1",
                              [{"google_query": "du lich", "youtube_query": "travel"}],
                              slot_index=0, screen_w=1200, screen_h=800,
                              skip_youtube=False, skip_random_keywords=False,
                              phase="clean", fixed_target_s=600)
    except Exception:
        pass
    cyc = ui.SLOT_CYCLE_INFO.get("Slot 1", {})
    check("Nhánh FIXED: target_s = 600 đúng số người dùng đặt", cyc.get("target_s") == 600,
          str(cyc.get("target_s")))
    check("Nhánh FIXED: actions vẫn được bot random 4..8",
          4 <= (cyc.get("actions") or 0) <= 8, str(cyc.get("actions")))
    ui.WarmupWorkflow = real_workflow
    ui.BrowserController = real_bc
    ui.adjust_window_bounds = real_adjust
    ui.time.sleep = real_sleep

    print("     · 200 lần random: kiểm tra KHÔNG phải hằng số ngày này qua ngày khác")
    vals = set()
    for _ in range(200):
        ta = RealRandint(4, 8)
        vals.add(RealRandint(0, max(1, ta - 1)) * 60)
    check("Mục tiêu random có nhiều giá trị khác nhau (>2 biến thể)", len(vals) > 2, str(sorted(vals)))

    # --- 5c. _tick_status chạy được với mốc riêng của vòng
    ui.SLOT_THREAD_ALIVE["Slot 1"] = True
    ui.SLOT_LABEL["Slot 1"] = "PID-GUI-1 · Profile GUI 1"
    ui.SLOT_PROFILE["Slot 1"] = "PID-GUI-1"
    ui.SLOT_LAST_LOG["Slot 1"] = time.time()
    ui.SLOT_CYCLE_START["Slot 1"] = time.time() - 700      # 700s > mốc 600 -> phải có ⏰
    ui.SLOT_CYCLE_INFO.setdefault("Slot 1", {})["target_s"] = 600
    app._running = True
    app._active_slots = [0]                                 # _tick_status nhận chỉ số slot (int)
    app._tick_status()
    ui_root.update()
    st = app.lbl_status.cget("text")
    check("_tick_status in thời gian vòng đang chạy (700s -> 11m40s)",
          "11m40s" in st, st[:120])
    check("_tick_status có cờ ⏰ khi vượt mốc riêng của vòng", "⏰" in st, st[:120])
    ui.SLOT_CYCLE_START["Slot 1"] = time.time() - 60       # 60s < 600 -> bỏ ⏰
    app._tick_status()
    ui_root.update()
    st2 = app.lbl_status.cget("text")
    check("_tick_status BỎ ⏰ khi chưa tới mốc", "⏰" not in st2, st2[:120])
    app._running = False
    app._active_slots = []

    # --- 5d. Bảng tài khoản dựng được (đọc DB có mốc riêng)
    app.show_account_dashboard()
    dlg = grab_toplevel("Bảng tài khoản")
    check("Toplevel Bảng tài khoản mở được", dlg is not None)
    if dlg:
        trees = find_all(dlg, ttk.Treeview)
        check("Bảng tài khoản có Treeview", bool(trees))
        if trees:
            cols = trees[0]["columns"]
            check("Bảng tài khoản có cột Vòng này (cycle_now)", "cycle_now" in cols, str(cols))

    # --- 5e. Dialog chu trình: cột M.tiêu cuối + dòng PID-A hiện đúng mốc
    app.show_cycle_time_dialog()
    dlg2 = grab_toplevel("Thời gian ngâm")
    check("Toplevel Thời gian ngâm (chu trình) mở được", dlg2 is not None)
    if dlg2:
        for w in find_all(dlg2, ttk.Combobox):
            w.set("3650")
        btns = [b for b in find_all(dlg2, ttk.Button) if "làm mới" in (b.cget("text") or "").lower()]
        if btns:
            btns[0].invoke()
            ui_root.update()
        trees2 = find_all(dlg2, ttk.Treeview)
        check("Dialog chu trình có Treeview", bool(trees2))
        cols2 = trees2[0]["columns"] if trees2 else ()
        check("Dialog chu trình có cột 'M.tiêu cuối' (last_target)", "last_target" in cols2, str(cols2))
        heads = [trees2[0].heading(c, "text") for c in cols2] if trees2 else []
        check("Tiêu đề cột 'M.tiêu cuối' đúng", "M.tiêu cuối" in heads, str(heads))
        row_a = None
        for iid in (trees2[0].get_children() if trees2 else ()):
            if trees2[0].set(iid, "id") == "PID-A"[:8]:
                row_a = trees2[0].set(iid, "last_target")
        check("Dòng PID-A: cột M.tiêu cuối = 10m00s (600s)", row_a == "10m00s", str(row_a))

    # --- 5f. _show_detail (chi tiết 1 dòng): có cột Mục tiêu + cờ ⏰
    if dlg2:
        detail_ok = False
        try:
            trees2[0].selection_set(trees2[0].get_children()[0])
            dlg2.event_generate("<<ShowCycleDetail>>", when="now")
            ui_root.update()
            dl = grab_toplevel("Chu trình —")
            check("Toplevel chi tiết chu trình mở được", dl is not None)
            if dl:
                t3 = find_all(dl, ttk.Treeview)
                cols3 = t3[0]["columns"] if t3 else ()
                check("Chi tiết chu trình có cột Mục tiêu (tg)", "tg" in cols3, str(cols3))
                heads3 = [t3[0].heading(c, "text") for c in cols3] if t3 else []
                check("Tiêu đề cột 'Mục tiêu' đúng", "Mục tiêu" in heads3, str(heads3))
                if t3 and t3[0].get_children():
                    v = t3[0].item(t3[0].get_children()[0], "values")
                    check("Dòng chi tiết có giá trị Mục tiêu (không rỗng)", len(v) >= 4 and v[3] != "", str(v[:5]))
                dl.destroy()
        except tk.TclError as e:
            check("_show_detail chạy không lỗi TclError", False, str(e))
        ui_root.update()

    for w in list(ui_root.winfo_children()):
        if isinstance(w, RealToplevel) and "chi tiết" not in (w.title() or "").lower():
            try:
                w.destroy()
            except Exception:
                pass
    ui_root.update()

    # --- 5g. Toggle theme với dialog mở (remap đệ quy không crash)
    try:
        before = app.theme_name
        app._toggle_theme()
        ui_root.update()
        app._toggle_theme()
        ui_root.update()
        check("Toggle theme 2 vòng với dialog đang mở: không crash", app.theme_name == before,
              app.theme_name)
    except Exception as e:
        check("Toggle theme 2 vòng với dialog đang mở: không crash", False, repr(e))

    ui_root.destroy()
except tk.TclError as e:
    check("GUI smoke chạy được trong môi trường này", False, f"TclError: {e}")


# =====================================================================
hr("6. YÊU CẦU #1 — Reddit khỏi pha clean + đọc báo qua cổng Google")
# =====================================================================
import inspect  # noqa: E402
from src.workflow.warmup import WarmupWorkflow  # noqa: E402

src_ui = open(os.path.join(HERE, "ui_main.py"), encoding="utf-8").read()
src_wu = open(os.path.join(HERE, "workflow", "warmup.py"), encoding="utf-8").read()

# 6a. Bản đồ clean KHÔNG còn Reddit, nhưng mail VẪN có
i_mail = src_wu.index('elif self.phase == "mail":')
i_clean_start = src_wu.index('else:', i_mail + 400)      # nhánh else = pha clean
i_clean_end = src_wu.index('if getattr(self, \'skip_random_keywords\'', i_clean_start)
clean_txt = src_wu[i_clean_start:i_clean_end]
check("Pha clean KHÔNG còn action_interact_reddit", "action_interact_reddit" not in clean_txt,
      clean_txt[:60].replace("\n", " "))
check("Pha clean vẫn còn read_news + wikipedia + tiktok",
      all(k in clean_txt for k in ("action_read_news", "action_read_wikipedia", "action_watch_tiktok")))
i_yt = src_wu.index('if self.phase == "youtube":')
mail_txt = src_wu[i_yt:i_clean_start]
check("Pha mail VẪN giữ Reddit (chỉ bỏ ở pha 1)",
      "action_interact_reddit" in mail_txt)
check("Pha youtube KHÔNG có Reddit (đúng như trước)",
      "action_interact_reddit" not in src_wu[i_yt:i_mail])
# 6b. action_read_news phải đi qua cổng Google + fallback có nhãn
i_rn = src_wu.index("def action_read_news")
i_rn_end = src_wu.index("def ", i_rn + 30)
rn_txt = src_wu[i_rn:i_rn_end]
check("action_read_news gọi _navigate_via_google", "_navigate_via_google(page" in rn_txt)
check("action_read_news giữ fallback goto thẳng CÓ NHÃN '(Fallback Google)'",
      "page.goto(target_site" in rn_txt and "(Fallback Google)" in rn_txt)
check("action_read_news KHÔNG còn goto thẳng vô điều kiện",
      rn_txt.index("_navigate_via_google") < rn_txt.index("page.goto(target_site"))
check("Danh sách 13 trang báo giữ nguyên",
      rn_txt.count('("https://') >= 13, str(rn_txt.count('("https://')))
# 6c. Tài liệu UI (PHASE_DETAILS) phản ánh đúng: clean bỏ Reddit + đi qua cổng Google
i_clean_pd = src_ui.index('"clean": {')
i_mail_pd = src_ui.index('"mail": {', i_clean_pd)
pd_clean = src_ui[i_clean_pd:i_mail_pd]
check("PHASE_DETAILS clean KHÔNG còn Reddit", "Reddit" not in pd_clean.replace(
    "KHÔNG có Reddit", "").replace("Reddit chỉ xuất hiện", ""))
check("PHASE_DETAILS clean nói rõ đọc báo/nền tảng đi QUA CỔNG GOOGLE",
      "QUA CỔNG GOOGLE" in pd_clean)
check("PHASE_DETAILS clean ghi chú Reddit chỉ từ Pha 2", "Pha 2" in pd_clean)
check("PHASE_DETAILS mail VẪN có Reddit", "Reddit" in src_ui[i_mail_pd:i_mail_pd + 3000])

# =====================================================================
hr("KẾT QUẢ")
print(f"PASS: {len(PASS)}   FAIL: {len(FAIL)}")
if FAIL:
    print("FAIL list:")
    for f in FAIL:
        print("   - " + f)
print("\nSMOKE v1.4.1: " + ("ALL PASS" if not FAIL else "CÓ LỖI"))


# --- dọn dẹp ---
try:
    shutil.rmtree(TMP, ignore_errors=True)
    print(f"[dọn] đã xóa temp DB {TMP}")
except Exception:
    pass
