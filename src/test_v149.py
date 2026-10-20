"""SMOKE v1.4.9 — BOARD THỜI LƯỢNG CHẠY (tab riêng trong notebook + get_cycle_lifetime_stats).

Cô lập tuyệt đối: GPM_BOT_DATA_DIR = temp\\data (DB + config temp).
DB THẬT ở repo-root được hash trước/sau — phải y hệt từng byte.

Chạy:  python src/test_v149.py
"""
import datetime
import hashlib
import io
import os
import shutil
import sys
import tempfile
import time
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

TMP = tempfile.mkdtemp(prefix="gpm_v149_")
DATA_DIR = os.path.join(TMP, "data")
os.makedirs(DATA_DIR, exist_ok=True)
REAL_DB = os.path.join(REPO, "data", "agent_logs.db")
real_db_hash_before = ""
if os.path.exists(REAL_DB):
    real_db_hash_before = hashlib.sha256(open(REAL_DB, "rb").read()).hexdigest()

os.environ["GPM_BOT_DATA_DIR"] = DATA_DIR

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  [PASS] " if cond else "  [FAIL] ") + name + (f"  ({extra})" if extra else ""))


def hr(t):
    print("\n" + "=" * 68)
    print(t)
    print("=" * 68)


def find_all(widget, kind, out=None):
    out = out if out is not None else []
    for c in widget.winfo_children():
        if isinstance(c, kind):
            out.append(c)
        find_all(c, kind, out)
    return out


root = None


def find_toplevel(title_frag):
    for w in root.winfo_children():
        if isinstance(w, tk.Toplevel) and title_frag.lower() in (w.title() or "").lower():
            return w
    return None


def click_btn(parent, text):
    for b in find_all(parent, ttk.Button):
        try:
            if (b.cget("text") or "").strip() == text:
                b.invoke()
                return True
        except Exception:
            pass
    for b in find_all(parent, tk.Button):
        try:
            if (b.cget("text") or "").strip() == text:
                b.invoke()
                return True
        except Exception:
            pass
    return False


_TODAY = datetime.date.today().isoformat()
_YEST = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
_OLD = (datetime.date.today() - datetime.timedelta(days=60)).isoformat()

# =====================================================================
hr("1. DB — get_cycle_lifetime_stats() (toàn thời, không lọc cửa sổ ngày)")
from src.database.db_handler import DatabaseHandler  # noqa: E402

db = DatabaseHandler()
check("DB temp nằm trong GPM_BOT_DATA_DIR", db.db_path.startswith(DATA_DIR), db.db_path)

# PID-A: 3 vòng — 2 hôm nay, 1 hôm qua; actions 5+2+0 = 7; 2 ngày khác nhau
db.log_cycle("PID-A", f"{_YEST}T09:00:00", f"{_YEST}T09:10:00", 600.0, "ok",
             actions=0, phase="clean", target_s=900)
db.log_cycle("PID-A", f"{_TODAY}T09:00:00", f"{_TODAY}T09:20:00", 1200.0, "ok",
             actions=5, phase="clean", target_s=900)
db.log_cycle("PID-A", f"{_TODAY}T10:00:00", f"{_TODAY}T10:05:00", 300.0, "error",
             actions=2, phase="clean", error="boom", target_s=None)
# PID-B: 1 vòng CŨ (60 ngày trước) -> phải có trong toàn thời nhưng KHÔNG trong cửa sổ 30 ngày
db.log_cycle("PID-B", f"{_OLD}T09:00:00", f"{_OLD}T11:30:00", 9000.0, "stopped",
             actions=8, phase="mail")
# PID-C: vòng có actions NULL (col COALESCE)
db.log_cycle("PID-C", f"{_TODAY}T08:00:00", f"{_TODAY}T08:00:11", 11.0, "ok",
             actions=None, phase="youtube")

life = db.get_cycle_lifetime_stats()
a = life.get("PID-A", {})
check("PID-A cycles_all = 3", a.get("cycles_all") == 3, str(a))
check("PID-A total_all_s = 2100", abs((a.get("total_all_s") or 0) - 2100.0) < 1e-6, str(a.get("total_all_s")))
check("PID-A today_s = 1500 (2 vòng hôm nay)", abs((a.get("today_s") or 0) - 1500.0) < 1e-6, str(a.get("today_s")))
check("PID-A actions_all = 7", a.get("actions_all") == 7, str(a.get("actions_all")))
check("PID-A first_at = hôm qua", (a.get("first_at") or "").startswith(_YEST), str(a.get("first_at")))
check("PID-A days_active = 2", a.get("days_active") == 2, str(a.get("days_active")))
b = life.get("PID-B", {})
check("PID-B cycles_all = 1 (vòng 60 ngày vẫn tính toàn thời)", b.get("cycles_all") == 1, str(b))
check("PID-B today_s = 0", abs((b.get("today_s") or 0)) < 1e-6, str(b.get("today_s")))
check("PID-B last_status = stopped (toan thoi, ngoai cua so 30 ngay)",
      b.get("last_status") == "stopped", str(b.get("last_status")))
check("PID-B last_duration_s = 9000", abs((b.get("last_duration_s") or 0) - 9000.0) < 1e-6,
      str(b.get("last_duration_s")))
check("PID-B last_at nam trong ngay 60 truoc", (b.get("last_at") or "").startswith(_OLD),
      str(b.get("last_at")))
check("PID-A last_error = boom (row cuoi toan thoi)", a.get("last_error") == "boom",
      str(a.get("last_error")))
check("PID-A last_status = error", a.get("last_status") == "error", str(a.get("last_status")))
c = life.get("PID-C", {})
check("PID-C actions NULL -> actions_all = 0 (COALESCE)", c.get("actions_all") == 0, str(c))
check("PID-C total_all_s = 11", abs((c.get("total_all_s") or 0) - 11.0) < 1e-6, str(c.get("total_all_s")))

win30 = db.get_cycle_summary(days=30, target_s=0)
check("get_cycle_summary 30 ngày có PID-A", "PID-A" in win30)
check("get_cycle_summary 30 ngày KHÔNG có PID-B (vòng cũ)", "PID-B" not in win30, str(list(win30)))
check("PID-A cycles trong 30 ngày = 3", win30.get("PID-A", {}).get("cycles") == 3,
      str(win30.get("PID-A")))
check("PID-A last_status = error (row id lớn nhất)", win30.get("PID-A", {}).get("last_status") == "error",
      str(win30.get("PID-A", {}).get("last_status")))
check("PID-A last_error = boom", win30.get("PID-A", {}).get("last_error") == "boom")
win_all = db.get_cycle_summary(days=3650, target_s=0)
check("cửa sổ 3650 ngày có PID-B", "PID-B" in win_all)
check("PID-B over = 0 (mốc NULL + target_s=0 -> không đếm oan)",
      win_all.get("PID-B", {}).get("over") == 0, str(win_all.get("PID-B")))

# activity cho drill-down
db.log_activity("PID-A", "action_watch_tiktok", "TikTok", "https://www.tiktok.com/foryou", "v1",
                status="ok", duration_s=30.0)
db.log_activity("PID-A", "action_watch_tiktok", "TikTok", "https://www.tiktok.com/foryou", "v2",
                status="error", duration_s=12.0, error="loi tiktok")
db.log_activity("PID-A", "read_news", "cafef.vn", "https://cafef.vn/bai-1", "bai 1",
                status="ok", duration_s=90.0)
act = db.get_activity_summary("PID-A", days=30)
check("get_activity_summary PID-A = 2 loại hành động", len(act) == 2, str(len(act)))
tk_row = next((r for r in act if r.get("action") == "action_watch_tiktok"), {})
check("TikTok count = 2", tk_row.get("count") == 2, str(tk_row))
check("TikTok errors = 1", tk_row.get("errors") == 1, str(tk_row))
check("TikTok total_duration_s = 42", abs((tk_row.get("total_duration_s") or 0) - 42.0) < 1e-6,
      str(tk_row.get("total_duration_s")))

# =====================================================================
hr("2. GUI — tab board + tab giai đoạn tồn tại, đủ 15 cột (v1.5.0 +Giai đoạn)")
import ui_main as ui  # noqa: E402

app = ui.AutomationApp(root := tk.Tk())
root.update()
check("AutomationApp khởi tạo OK", hasattr(app, "board_frame") and hasattr(app, "board_tree"))
tabs = list(app.notebook.tabs())
# v1.5.0: thứ tự chủ đích = MAIN -> (slots) -> THỜI LƯỢNG CHẠY -> GIAI ĐOẠN NGÂM.
# Tab giai đoạn NỐI SAU bảng thời lượng, nên board giờ là tab Á CUỐI.
check("notebook có >= 3 tab (MAIN + board + stage)", len(tabs) >= 3, str(len(tabs)))
check("tab CUỐI là giai đoạn", "GIAI ĐOẠN" in app.notebook.tab(tabs[-1], "text"),
      repr(app.notebook.tab(tabs[-1], "text")))
check("tab Á CUỐI là board thời lượng", "THỜI LƯỢNG" in app.notebook.tab(tabs[-2], "text"),
      repr(app.notebook.tab(tabs[-2], "text")))
check("board là con trực tiếp của notebook", app.board_frame in app.notebook.winfo_children())
check("stage là con trực tiếp của notebook", app.stage_frame in app.notebook.winfo_children())
check("board_frame == tab áp chót", str(app.board_frame) in tabs[-2],
      repr(app.notebook.tab(tabs[-2], "text")))
check("stage_frame == tab cuối", str(app.stage_frame) in tabs[-1],
      repr(app.notebook.tab(tabs[-1], "text")))
tree = app.board_tree
cols = list(tree.cget("columns"))
check("board có đúng 15 cột", len(cols) == 15 == len(app.BOARD_COLUMNS), str(cols))
check("cột khớp BOARD_COLUMNS", tuple(cols) == app.BOARD_COLUMNS, str(cols))
check("mọi cột có heading riêng", all(str(tree.heading(c, "text")).strip() for c in cols))
check("board KHÔNG đăng ký vào log_boxes", "THỜI LƯỢNG CHẠY" not in app.log_boxes,
      str(list(app.log_boxes)))

# Nạp checklist giả để test cột Tên/Nhóm
app.profile_rows = [
    {"id": "PID-A", "name": "Profile ngâm A", "firefox": False, "group": "Mail lô đang ngâm",
     "hidden": False, "var": None, "frame": None},
    {"id": "PID-B", "name": "Profile ngâm B", "firefox": False, "group": "Seeding",
     "hidden": False, "var": None, "frame": None},
    {"id": "PID-D", "name": "Profile chưa chạy", "firefox": False, "group": "",
     "hidden": False, "var": None, "frame": None},
]
btn = [b for b in find_all(app.board_frame, ttk.Button) if (b.cget("text") or "") == "Làm mới"][0]
btn.invoke()
root.update()
rows = list(tree.get_children())
check("board liệt kê 4 dòng (3 checklist + PID-C chỉ có trong DB)", len(rows) == 4, str(len(rows)))
by_pid = {tree.set(iid, "id"): iid for iid in rows}
check("có đủ 4 ID 8 ký tự", set(by_pid) == {"PID-A", "PID-B", "PID-C", "PID-D"}, str(set(by_pid)))
ra = by_pid["PID-A"]
check("cột Tên lấy từ checklist", tree.set(ra, "name") == "Profile ngâm A", tree.set(ra, "name"))
check("cột Nhóm lấy từ checklist", tree.set(ra, "group") == "Mail lô đang ngâm"[:16],
      tree.set(ra, "group"))
check("cột Số vòng (30 ngày) = 3", tree.set(ra, "cycles") == "3", repr(tree.set(ra, "cycles")))
check("cột Tổng mọi thời = 35m 00s", tree.set(ra, "total_all") == "35m00s", tree.set(ra, "total_all"))
check("cột Hôm nay = 25m 00s", tree.set(ra, "today") == "25m00s", tree.set(ra, "today"))
check("cột Hành động lũy kế = 7", tree.set(ra, "actions") == "7", tree.set(ra, "actions"))
check("cột Ngày đầu = hôm qua", tree.set(ra, "first") == _YEST, tree.set(ra, "first"))
check("cột Ngày ngâm = 2", tree.set(ra, "days") == "2", tree.set(ra, "days"))
check("cột Kết quả = LOI (vòng cuối error)", tree.set(ra, "result").startswith("LOI"),
      tree.set(ra, "result"))
check("cột Xong lúc có timestamp", len(tree.set(ra, "last_at")) == 19, tree.set(ra, "last_at"))
rb = by_pid["PID-B"]
check("PID-B (vòng 60 ngày) trống cột Số vòng cửa sổ 30 ngày", tree.set(rb, "cycles") == "",
      repr(tree.set(rb, "cycles")))
check("PID-B vẫn có Tổng mọi thời 2h 30m", tree.set(rb, "total_all") == "2h30m",
      tree.set(rb, "total_all"))
check("PID-B Kết quả = Dung giua vong (ASCII, không emoji)", tree.set(rb, "result") == "Dung giua vong",
      tree.set(rb, "result"))
rc = by_pid["PID-C"]
check("PID-C actions NULL -> cột Hành động rỗng", tree.set(rc, "actions") == "",
      repr(tree.set(rc, "actions")))
rd = by_pid["PID-D"]
check("PID-D (chưa chạy) không bị ép nhóm", tree.set(rd, "group") == "", repr(tree.set(rd, "group")))
check("PID-D Tổng mọi thời rỗng", tree.set(rd, "total_all") == "", repr(tree.set(rd, "total_all")))
check("PID-D Kết quả rỗng (chưa chạy)", tree.set(rd, "result") == "", repr(tree.set(rd, "result")))
st = app._board_status.cget("text")
check("dòng trạng thái có '4 profile'", st.startswith("4 profile"), st)
check("dòng trạng thái có 'mọi thời'", "mọi thời" in st, st)
check("dòng trạng thái có 'hành động'", "hành động" in st, st)

# =====================================================================
hr("3. Cột 'Đang chạy' realtime + ⏰ vượt mục tiêu của CHÍNH vòng")
for m in (ui.SLOT_PROFILE, ui.SLOT_CYCLE_START, ui.SLOT_CYCLE_INFO, ui.SLOT_THREAD_ALIVE):
    m.clear()
ui.SLOT_PROFILE["Slot 1"] = "PID-A"
ui.SLOT_CYCLE_START["Slot 1"] = time.time() - 100
ui.SLOT_CYCLE_INFO["Slot 1"] = {"target_s": 300}
ui.SLOT_THREAD_ALIVE["Slot 1"] = True
btn.invoke()
root.update()
by_pid = {tree.set(iid, "id"): iid for iid in tree.get_children()}
run_a = tree.set(by_pid["PID-A"], "running")
check("PID-A đang chạy -> cột 'Đang chạy' có thời lượng", run_a.startswith("1m40s"), repr(run_a))
check("chưa vượt mốc 300s -> KHÔNG có ⏰", "⏰" not in run_a, repr(run_a))

ui.SLOT_CYCLE_START["Slot 1"] = time.time() - 400
btn.invoke()
root.update()
by_pid = {tree.set(iid, "id"): iid for iid in tree.get_children()}
run_a2 = tree.set(by_pid["PID-A"], "running")
check("vượt mốc riêng 300s -> có ⏰", "⏰" in run_a2, repr(run_a2))

ui.SLOT_THREAD_ALIVE["Slot 1"] = False
btn.invoke()
root.update()
by_pid = {tree.set(iid, "id"): iid for iid in tree.get_children()}
check("thread chết -> cột 'Đang chạy' rỗng", tree.set(by_pid["PID-A"], "running") == "",
      repr(tree.set(by_pid["PID-A"], "running")))
ui.SLOT_PROFILE.pop("Slot 1", None)
ui.SLOT_CYCLE_START.pop("Slot 1", None)
ui.SLOT_CYCLE_INFO.pop("Slot 1", None)
ui.SLOT_THREAD_ALIVE.pop("Slot 1", None)
btn.invoke()
root.update()
by_pid = {tree.set(iid, "id"): iid for iid in tree.get_children()}
check("xong -> cột 'Đang chạy' rỗng trở lại", tree.set(by_pid["PID-A"], "running") == "")

# =====================================================================
hr("4. Sort theo cột (số vs chuỗi) + đảo chiều + marker ▲/▼")
# Tk không có API Python để đọc heading command -> gọi qua Tcl.
raw = tree.heading("total_all")
tcl_cmd = raw.get("command") if isinstance(raw, dict) else None
check("heading cột total_all có command sort", bool(tcl_cmd), str(raw)[:80])
tree.tk.call(tcl_cmd)
root.update()
desc = [app._board_raw.get(i, {}).get("total_all") for i in tree.get_children()]
check("lần 1 sort giảm dần theo Tổng mọi thời (float, None cuối)",
      desc[:-1] == sorted(desc[:-1], reverse=True) and desc[-1] is None, str(desc))
check("PID-B (2h30m) đứng đầu", tree.set(tree.get_children()[0], "id") == "PID-B",
      tree.set(tree.get_children()[0], "id"))
check("header hiện ▼ khi sort giảm dần",
      str(tree.heading("total_all", "text")).endswith("▼"), repr(tree.heading("total_all", "text")))
tree.tk.call(tcl_cmd)
root.update()
asc = [app._board_raw.get(i, {}).get("total_all") for i in tree.get_children()]
check("click lại -> đảo lên dần (so float, None cuoi cung)",
      asc[:-1] == sorted(asc[:-1]) and asc[-1] is None, str(asc))
check("header hiện ▲ khi sort tăng dần",
      str(tree.heading("total_all", "text")).endswith("▲"), repr(tree.heading("total_all", "text")))
# Cột chuỗi
cmd_name = tree.heading("name").get("command")
tree.tk.call(cmd_name)
root.update()
names = [tree.set(i, "name") for i in tree.get_children()]
check("sort cột Tên (chuỗi) hợp lệ", len(names) == 4 and all(names), str(names))
check("marker chỉ còn ở 1 cột đang sort",
      sum(1 for c in app.BOARD_COLUMNS if str(tree.heading(c, "text"))[-1] in "▲▼") == 1,
      str([tree.heading(c, "text") for c in app.BOARD_COLUMNS]))
check("sort không làm mất dòng", len(tree.get_children()) == 4)

# =====================================================================
hr("5. Drill-down phân tích hành động (double-click / virtual event)")
tree.selection_set(by_pid["PID-A"])
tree.event_generate("<<ShowBoardBreakdown>>")
root.update()
dlg = find_toplevel("Hành động")
check("dialog phân tích mở", dlg is not None)
t2 = None
if dlg:
    t2 = find_all(dlg, ttk.Treeview)[0]
    rows2 = list(t2.get_children())
    check("dialog có 2 loại hành động của PID-A", len(rows2) == 2, str(len(rows2)))
    plat = {t2.set(i, "platform") for i in rows2}
    check("có TikTok + cafef.vn", plat == {"TikTok", "cafef.vn"}, str(plat))
    tik = [i for i in rows2 if t2.set(i, "platform") == "TikTok"][0]
    check("TikTok số lần = 2", t2.set(tik, "count") == "2", t2.set(tik, "count"))
    check("TikTok lỗi = 1", t2.set(tik, "errors") == "1", t2.set(tik, "errors"))
    check("TikTok tổng = 42s", t2.set(tik, "total") == "42s", t2.set(tik, "total"))
    lbls = " ".join(str(l.cget("text")) for l in find_all(dlg, tk.Label) + find_all(dlg, ttk.Label))
    check("dialog ghi cửa sổ ngày", "ngày" in lbls, lbls[:120])
    check("nút Đóng có trong dialog", click_btn(dlg, "Đóng"))
    root.update()
    check("Đóng làm dialog biến mất", find_toplevel("Hành động") is None)
# Không chọn dòng -> không mở dialog
tree.selection_remove(*tree.get_children())
tree.event_generate("<<ShowBoardBreakdown>>")
root.update()
check("không chọn dòng -> KHÔNG mở dialog", find_toplevel("Hành động") is None)

# =====================================================================
hr("6. Combobox cửa sổ ngày + selection SỐNG SÓT qua lần tạo lại tab")
cbo = app.cbo_board_days
check("combobox readonly", str(cbo.cget("state")) == "readonly", repr(cbo.cget("state")))
check("values = 7/30/90/Tất cả", list(cbo.cget("values")) == ["7", "30", "90", "Tất cả"],
      str(cbo.cget("values")))
cbo.set("Tất cả")
cbo.event_generate("<<ComboboxSelected>>")
root.update()
by_pid_all = {tree.set(i, "id"): i for i in tree.get_children()}
check("'Tất cả' -> PID-B có Số vòng = 1", tree.set(by_pid_all["PID-B"], "cycles") == "1",
      repr(tree.set(by_pid_all["PID-B"], "cycles")))
st_all = app._board_status.cget("text")
check("'Tất cả' -> trạng thái ghi 5 vòng", "5 vòng" in st_all, st_all)
cbo.set("7")
cbo.event_generate("<<ComboboxSelected>>")
root.update()
check("cửa sổ 7 ngày -> PID-B lại trống Số vòng",
      tree.set({tree.set(i, "id"): i for i in tree.get_children()}["PID-B"], "cycles") == "")
# Tạo lại tab (Start làm việc này) -> phải giữ "7"
old_frame = app.board_frame
app._create_board_tab()
root.update()
check("tạo lại tab giữ cửa sổ đã chọn ('7')", app.var_board_days.get() == "7",
      app.var_board_days.get())
check("frame board cũ đã bị destroy", not old_frame.winfo_exists())
# v1.5.0: _create_board_tab() luôn add() ở cuối -> board tạm thời là tab CUỐI; tab giai
# đoạn được nối lại SAU board (giống start_automation) để khôi phục thứ tự chủ đích.
app._create_stage_tab()
root.update()
check("thứ tự khôi phục: board áp chót, giai đoạn cuối",
      "THỜI LƯỢNG" in app.notebook.tab(app.notebook.tabs()[-2], "text") and
      "GIAI ĐOẠN" in app.notebook.tab(app.notebook.tabs()[-1], "text"),
      str([app.notebook.tab(t, "text").strip() for t in app.notebook.tabs()]))
check("board mới hiển thị lại dữ liệu", len(app.board_tree.get_children()) == 4,
      str(len(app.board_tree.get_children())))
check("notebook không nhân đôi tab board",
      sum(1 for t in app.notebook.tabs() if "THỜI LƯỢNG" in app.notebook.tab(t, "text")) == 1)
check("notebook không nhân đôi tab giai đoạn",
      sum(1 for t in app.notebook.tabs() if "GIAI ĐOẠN" in app.notebook.tab(t, "text")) == 1)

# =====================================================================
hr("7. Bất biến chỉ số tab khi Start (quên tabs[1:] rồi tạo slot + board + stage lại)")
app._create_tab("Slot 1")
app._create_tab("Slot 2")
for t in list(app.notebook.tabs())[1:]:
    app.notebook.forget(t)
for i in range(2):
    app._create_tab(f"Slot {i + 1}")
app._create_board_tab()
app._create_stage_tab()   # v1.5.0: start_automation cũng nối lại tab giai đoạn
root.update()
tabs = list(app.notebook.tabs())
texts = [app.notebook.tab(t, "text").strip() for t in tabs]
check("thứ tự tab = MAIN, Slot 1, Slot 2, board, giai đoạn",
      texts == ["MAIN", "Slot 1", "Slot 2", "THỜI LƯỢNG CHẠY", "GIAI ĐOẠN NGÂM"], str(texts))
app.update_tab_name(0, "Profile ngâm A")
app.update_tab_name(1, "Profile ngâm B")
root.update()
root.update()
texts = [app.notebook.tab(t, "text").strip() for t in app.notebook.tabs()]
check("tabs()[slot+1] vẫn đúng sau khi board + stage được nối lại",
      texts[1] == "Profile ngâm A" and texts[2] == "Profile ngâm B", str(texts))
check("giai đoạn vẫn CUỐI cùng sau update_tab_name", "GIAI ĐOẠN" in texts[-1], str(texts))

# =====================================================================
hr("8. Kiểm tĩnh source (wire + chống regression)")
src_ui = io.open(os.path.join(HERE, "ui_main.py"), encoding="utf-8").read()
src_db = io.open(os.path.join(HERE, "database", "db_handler.py"), encoding="utf-8").read()
check("__init__ gọi _create_board_tab() sau _create_tab('MAIN')",
      src_ui.index('self._create_tab("MAIN")') < src_ui.index("self._create_board_tab()",
                                                             src_ui.index("def __init__")))
check("_create_board_tab duoc goi o ca __init__ lan start_automation",
      src_ui.count("self._create_board_tab()") == 2,
      str(src_ui.count("self._create_board_tab()")))
i_forget = src_ui.index("for tab in self.notebook.tabs()[1:]")
i_board = src_ui.index("self._create_board_tab()", i_forget)
check("board được tạo SAU vòng forget + vòng slot trong start_automation",
      i_forget < i_board < src_ui.index("def run_thread_pool"), f"{i_forget} < {i_board}")
check("messagebox trong board dùng parent=self.root (không truyền ttk.Frame)",
      'f"Không đọc được activity: {e}", parent=self.root' in src_ui)
check("board bind virtual event cho test", "<<ShowBoardBreakdown>>" in src_ui)
check("board tự tươi 15s có gate winfo_exists",
      "if frame.winfo_exists():" in src_ui)
check("db_handler có get_cycle_lifetime_stats", "def get_cycle_lifetime_stats(self):" in src_db)
check("get_cycle_lifetime_stats là SELECT-only",
      "INSERT" not in src_db[src_db.index("def get_cycle_lifetime_stats"):
                            src_db.index("def get_last_cycle_targets")])
src_wu = io.open(os.path.join(HERE, "workflow", "warmup.py"), encoding="utf-8").read()
check("warmup.py KHÔNG bị đụng (không symbol board/giai đoạn nao)",
      not any(k in src_wu for k in ("_create_board_tab", "board_tree", "BOARD_COLUMNS",
                                    "get_cycle_lifetime_stats", "board_frame",
                                    "_create_stage_tab", "stage_tree", "STAGE_COLUMNS",
                                    "compute_stage", "log_stage_change")),
      str([k for k in ("_create_board_tab", "board_tree", "BOARD_COLUMNS",
                       "get_cycle_lifetime_stats", "board_frame",
                       "_create_stage_tab", "stage_tree", "STAGE_COLUMNS",
                       "compute_stage", "log_stage_change") if k in src_wu]))
i_stage = src_ui.index("self._create_stage_tab()", i_forget)
check("stage được tạo SAU board trong start_automation (board áp chót, stage cuối)",
      i_board < i_stage < src_ui.index("def run_thread_pool"), f"{i_board} < {i_stage}")
check("__init__ gọi _create_stage_tab() sau _create_board_tab()",
      src_ui.index("self._create_board_tab()", src_ui.index("def __init__")) <
      src_ui.index("self._create_stage_tab()", src_ui.index("def __init__")))
check("_create_stage_tab duoc goi o ca __init__ lan start_automation",
      src_ui.count("self._create_stage_tab()") == 2,
      str(src_ui.count("self._create_stage_tab()")))
check("start_automation cảnh báo lệch pha (chỉ hỏi, không tự đổi)",
      "Lệch chế độ ngâm" in src_ui and "Vẫn chạy với chế độ đã chọn?" in src_ui)
check("worker tự ghi mốc giai đoạn (log_stage_change source=auto)",
      'db.log_stage_change(' in src_ui and 'source="auto"' in src_ui)
check("db_handler có compute_stage / get_stage_overview / backfill_stage_tracking",
      all(k in src_db for k in ("def compute_stage(", "def get_stage_overview(",
                                "def backfill_stage_tracking(")))
check("migration stage có backup trước ALTER + abort khi backup fail",
      'backup_database(reason="pre-migration-stage' in src_db or
      ("_migrate_stage_tracking" in src_db and "BỎ QUA migration" in src_db))
lbl_board = app.notebook.tab(app.notebook.tabs()[-2], "text")
check("nhãn tab board ASCII + tiếng Việt, không emoji", "THỜI LƯỢNG CHẠY" in lbl_board, repr(lbl_board))
lbl_stage = app.notebook.tab(app.notebook.tabs()[-1], "text")
check("nhãn tab giai đoạn không emoji", "GIAI ĐOẠN NGÂM" in lbl_stage, repr(lbl_stage))

# =====================================================================
hr("9. Dọn dẹp + DB THẬT không bị đụng")
try:
    dlg.destroy()
except Exception:
    pass
root.update()
root.destroy()

real_db_hash_after = ""
if os.path.exists(REAL_DB):
    real_db_hash_after = hashlib.sha256(open(REAL_DB, "rb").read()).hexdigest()
check("hash DB THẬT trước == sau", real_db_hash_before == real_db_hash_after,
      f"{real_db_hash_before[:12]} vs {real_db_hash_after[:12]}")

for m in (ui.SLOT_PROFILE, ui.SLOT_LAST_LOG, ui.SLOT_LABEL, ui.SLOT_THREAD_ALIVE,
          ui.SLOT_CYCLE_START, ui.SLOT_CYCLE_INFO):
    m.clear()
shutil.rmtree(TMP, ignore_errors=True)
os.environ.pop("GPM_BOT_DATA_DIR", None)

print("\n" + "=" * 68)
print(f"KẾT QUẢ v1.4.9: PASS={len(PASS)}  FAIL={len(FAIL)}")
if FAIL:
    for f in FAIL:
        print("  [FAIL]", f)
    sys.exit(1)
print("SMOKE v1.4.9: ALL PASS")
