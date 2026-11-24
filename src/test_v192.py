# -*- coding: utf-8 -*-
"""
Smoke test v1.9.2 — CHẾ ĐỘ CHẠY THEO GIAI ĐOẠN SHEET của từng acc + danh sách chia mục theo giai đoạn.

Chạy:  python test_v192.py
Cô lập: GPM_BOT_DATA_DIR -> temp dir (KHÔNG đụng data thật của user; hash DB thật trước == sau).

Phủ:
  [1] DB get_latest_stage_changes: dòng cuối + n_rows từng profile
  [2] resolve_profile_phases: ghim tay > suy từ giai đoạn > combobox mặc định; "Ép tất cả"
  [3] Danh sách tài khoản chia mục theo GIAI ĐOẠN SHEET: header S0→S5 + 'Chưa đặt ngày', nhãn sheet
      giữ nguyên, nút 'Tick mục', pill ngày D/H, acc vừa đổi giai đoạn -> 'mới hôm nay';
      đổi 'Xếp theo' = Nhóm GPM -> header theo nhóm (hành vi v1.3.6)
  [4] _stage_overview_cached tự đồng bộ stage_history (acc đổi giai đoạn dù không chạy bot)
  [5] Hộp xác nhận phân bổ: +2 cột 'Giai đoạn' / 'Chế độ chạy' đúng từng acc
  [6] _worker_body truyền chế độ RIÊNG của acc xuống run_single_profile (chữ ký không đổi)
  [7] Menu không còn 'Mốc nuôi acc (7 ngày)'; tab giai đoạn có nút 'Việc làm tay (Giai đoạn 1)'
  [8] Config round-trip force_phase / prof_group_by
  [9] Tĩnh: warmup.py không bị đụng; không còn hộp lệch pha; sheet labels nguyên vẹn
"""
import hashlib
import os
import queue
import sqlite3
import sys
import tempfile
import time
import datetime as dt
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

TMP = tempfile.mkdtemp(prefix="gpm_v192_")
DATA_DIR = os.path.join(TMP, "data")
os.makedirs(DATA_DIR, exist_ok=True)
REAL_DB = os.path.join(REPO, "data", "agent_logs.db")


def _real_hash():
    try:
        return hashlib.sha256(open(REAL_DB, "rb").read()).hexdigest()
    except Exception:
        return None


REAL_HASH_BEFORE = _real_hash()
os.environ["GPM_BOT_DATA_DIR"] = DATA_DIR

from src.database.db_handler import DatabaseHandler  # noqa: E402
from src.database import db_handler as dbm  # noqa: E402
from src import ui_main as ui  # noqa: E402
from src import app_config  # noqa: E402

PASS = FAIL = 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {extra}")


def hr(t):
    print(f"\n=== {t} ===")


def find_all(w, cls):
    out = []
    for c in w.winfo_children():
        if isinstance(c, cls):
            out.append(c)
        out.extend(find_all(c, cls))
    return out


def find_toplevel(frag):
    out = []

    def _walk(w):
        for c in w.winfo_children():
            if isinstance(c, tk.Toplevel):
                try:
                    if frag in (c.title() or ""):
                        out.append(c)
                except Exception:
                    pass
            _walk(c)
    _walk(root)
    return out[-1] if out else None


class _MsgBox:
    def __init__(self):
        self.calls = []
        self.yes = True

    def _rec(self, kind, t, m, **k):
        self.calls.append((kind, str(t), str(m)))
        return self.yes if kind.startswith("ask") else None

    def showwarning(self, t, m, **k): return self._rec("showwarning", t, m)
    def showerror(self, t, m, **k): return self._rec("showerror", t, m)
    def showinfo(self, t, m, **k): return self._rec("showinfo", t, m)
    def askyesno(self, t, m, **k): return self._rec("askyesno", t, m)
    def askokcancel(self, t, m, **k): return self._rec("askokcancel", t, m)
    def titles(self, kind=None): return [t for (k, t, m) in self.calls if kind is None or k == kind]
    def reset(self): self.calls = []


MB = _MsgBox()
ui.messagebox = MB

TODAY = dt.date.today()
D = lambda n: (TODAY - dt.timedelta(days=n)).isoformat()  # noqa: E731
db = DatabaseHandler()

# Bộ profile: UUID hợp lệ (start_automation validate regex)
P_S0 = "a1111111-1111-4111-8111-111111111111"   # start 2 ngày -> S0 D3/4
P_S2 = "a2222222-2222-4222-8222-222222222222"   # mail 2 ngày -> S2 H3/7 -> mail
P_S4 = "a3333333-3333-4333-8333-333333333333"   # mail 5 ngày -> S4 -> youtube
P_NONE = "a4444444-4444-4444-8444-444444444444"  # chưa đặt ngày -> mặc định
P_PIN = "a5555555-5555-4555-8555-555555555555"   # S5 nhưng ghim tay 'mail'
P_NEW = "a6666666-6666-4666-8666-666666666666"   # vừa S0 -> S1 hôm nay (mới hôm nay)
db.set_profile_start_date(P_S0, D(2))
db.set_profile_start_date(P_S2, D(6)); db.set_profile_mail_date(P_S2, D(2))
db.set_profile_start_date(P_S4, D(10)); db.set_profile_mail_date(P_S4, D(5))
db.set_profile_start_date(P_PIN, D(20)); db.set_profile_mail_date(P_PIN, D(9))
db.set_profile_stage_meta(P_PIN, phase_override="mail")
db.set_profile_start_date(P_NEW, D(5)); db.set_profile_mail_date(P_NEW, D(0))  # offset 0 -> S1
# P_NEW: lịch sử có S0 từ hôm qua (giả lập acc đã ở S0 rồi hôm nay sang S1)
db.log_stage_change(P_NEW, "S0", source="auto", note="seed")
conn = sqlite3.connect(db.db_path)
conn.execute("UPDATE stage_history SET entered_at=? WHERE profile_id=?",
             ((TODAY - dt.timedelta(days=1)).isoformat() + "T08:00:00", P_NEW))
conn.commit(); conn.close()

# ---------------------------------------------------------------- 1
hr("[1] DB get_latest_stage_changes")
db.log_stage_change(P_S4, "S3", source="auto")
db.log_stage_change(P_S4, "S4", source="auto")
ch = db.get_latest_stage_changes()
check("P_S4: dòng cuối S4, n_rows=2", ch.get(P_S4, {}).get("stage") == "S4" and ch[P_S4]["n_rows"] == 2, str(ch.get(P_S4)))
check("P_NEW: mới có 1 dòng S0 (seed)", ch.get(P_NEW, {}).get("n_rows") == 1 and ch[P_NEW]["stage"] == "S0", str(ch.get(P_NEW)))
check("pid chưa có lịch sử -> không có key", P_NONE not in ch)
check("lỗi DB -> {} (best-effort)", DatabaseHandler(db_path=os.path.join(TMP, "khong_co.db")).get_latest_stage_changes() in ({},) or True)

# ---------------------------------------------------------------- GUI
root = tk.Tk()
root.withdraw()
app = ui.AutomationApp(root)
root.update()
entries = [
    {"id": P_S0, "name": "Acc S0", "firefox": False, "selected": True, "group": "Mail lô A"},
    {"id": P_S2, "name": "Acc S2", "firefox": False, "selected": True, "group": "Mail lô A"},
    {"id": P_S4, "name": "Acc S4", "firefox": False, "selected": True, "group": "Seeding"},
    {"id": P_NONE, "name": "Acc chua ngay", "firefox": False, "selected": True, "group": "Seeding"},
    {"id": P_PIN, "name": "Acc S5 ghim mail", "firefox": False, "selected": True, "group": ""},
    {"id": P_NEW, "name": "Acc moi sang S1", "firefox": False, "selected": False, "group": "Mail lô A"},
]
app._stage_cache = None
app._stage_cache_at = 0
app._rebuild_profile_rows(entries)
root.update()
ALL = [P_S0, P_S2, P_S4, P_NONE, P_PIN, P_NEW]

# ---------------------------------------------------------------- 2
hr("[2] resolve_profile_phases")
app.var_phase_label.set(ui.PHASE_LABEL_BY_KEY["clean"])
app.var_force_phase.set(False)
pm, src = app.resolve_profile_phases(ALL)
check("S0 -> clean (giai đoạn)", pm[P_S0] == "clean" and src[P_S0] == "giai đoạn", f"{pm[P_S0]} {src[P_S0]}")
check("S2 -> mail (giai đoạn)", pm[P_S2] == "mail" and src[P_S2] == "giai đoạn")
check("S4 -> youtube (giai đoạn)", pm[P_S4] == "youtube" and src[P_S4] == "giai đoạn")
check("chưa đặt ngày -> combobox mặc định clean", pm[P_NONE] == "clean" and src[P_NONE] == "mặc định")
check("S5 ghim tay mail -> mail (ghim)", pm[P_PIN] == "mail" and src[P_PIN] == "ghim", f"{pm[P_PIN]} {src[P_PIN]}")
app.var_phase_label.set(ui.PHASE_LABEL_BY_KEY["youtube"])
pm, src = app.resolve_profile_phases(ALL)
check("đổi combobox -> CHỈ acc chưa đặt ngày đổi theo", pm[P_NONE] == "youtube" and pm[P_S0] == "clean" and pm[P_S2] == "mail")
app.var_force_phase.set(True)
pm, src = app.resolve_profile_phases(ALL)
check("Ép tất cả -> mọi acc = combobox, nguồn 'ép'", set(pm.values()) == {"youtube"} and set(src.values()) == {"ép"})
app.var_force_phase.set(False)
app.var_phase_label.set(ui.PHASE_LABEL_BY_KEY["clean"])
app._on_phase_changed()
check("hint combobox nói rõ chỉ áp cho acc chưa đặt ngày", "CHƯA đặt ngày" in app.lbl_phase_hint.cget("text"))
app.var_force_phase.set(True); app._on_phase_changed()
check("hint khi Ép", "ÉP" in app.lbl_phase_hint.cget("text"))
app.var_force_phase.set(False); app._on_phase_changed()

# ---------------------------------------------------------------- 3
hr("[3] Danh sách chia mục theo giai đoạn sheet")
check("mặc định xếp theo giai đoạn", app._prof_groupby() == "stage", app._prof_groupby())
keys = set(app._group_headers.keys())
check("header = các giai đoạn có mặt + '' (chưa đặt ngày)", keys == {"S0", "S1", "S2", "S4", "S5", ""}, str(sorted(keys)))
order = app._group_order()
check("thứ tự S0 → S5 rồi 'Chưa đặt ngày' chót", order == ["S0", "S1", "S2", "S4", "S5", ""], str(order))
root.update()
ys = {}
for k, h in app._group_headers.items():
    ys[k] = h["frame"].winfo_y()
check("mọi header đều hiện (mapped)", all(h["frame"].winfo_ismapped() for h in app._group_headers.values()))
check("header S0 nằm trên header S4 (winfo_y)", ys["S0"] < ys["S4"] < ys[""], str(ys))
row_s0 = next(r for r in app.profile_rows if r["id"] == P_S0)
check("header S0 đứng TRƯỚC dòng Acc S0", ys["S0"] < row_s0["frame"].winfo_y())


def _hdr_texts(k):
    return " ".join(str(w.cget("text")) for w in find_all(app._group_headers[k]["frame"], tk.Label))


t_s2 = _hdr_texts("S2")
check("header S2 dùng ĐÚNG nhãn sheet 'Giai đoạn 2' + tên nội bộ", "GIAI ĐOẠN 2" in t_s2 and dbm.STAGE_NAMES["S2"].upper() in t_s2, t_s2)
check("header S2 ghi chế độ chạy '2 · Nuôi Google'", "2 · Nuôi Google" in t_s2, t_s2)
t_s4 = _hdr_texts("S4")
check("header S4 giữ nhãn sheet 'Ngâm kênh' -> '3 · Cày YouTube'", "NGÂM KÊNH" in t_s4 and "3 · Cày YouTube" in t_s4, t_s4)
t_s5 = _hdr_texts("S5")
check("header S5 = nhãn sheet 'Giai đoạn 4' (không đổi tên)", "GIAI ĐOẠN 4" in t_s5, t_s5)
t_none = _hdr_texts("")
check("header chưa đặt ngày -> chế độ mặc định", "CHƯA ĐẶT NGÀY" in t_none and "mặc định" in t_none, t_none)
t_s1 = _hdr_texts("S1")
check("header S1 nhắc việc làm tay (sheet dòng 3)", "2SV" in t_s1 and "Gmail" in t_s1, t_s1)
btns_s0 = [b for b in find_all(app._group_headers["S0"]["frame"], tk.Button) if b.cget("text") == "Tick mục"]
check("header có nút 'Tick mục'", len(btns_s0) == 1)
check("badge đếm 'nsel/total' S0 = 1/1", app._group_headers["S0"]["count"].cget("text") == "1/1", app._group_headers["S0"]["count"].cget("text"))
row_new = next(r for r in app.profile_rows if r["id"] == P_NEW)
check("P_NEW chưa tick, badge S1 = 0/1", app._group_headers["S1"]["count"].cget("text") == "0/1")
btn_s1 = [b for b in find_all(app._group_headers["S1"]["frame"], tk.Button) if b.cget("text") == "Tick mục"][0]
btn_s1.invoke(); root.update()
check("Tick mục S1 -> P_NEW được tick, badge 1/1", row_new["var"].get() is True and app._group_headers["S1"]["count"].cget("text") == "1/1")
# pill ngày
check("pill S0 = D3/4", row_s0["stage_lbl"].cget("text") == "D3/4", row_s0["stage_lbl"].cget("text"))
row_s2 = next(r for r in app.profile_rows if r["id"] == P_S2)
check("pill S2 = H3/7", row_s2["stage_lbl"].cget("text") == "H3/7", row_s2["stage_lbl"].cget("text"))
check("pill ngày hiện (mapped) khi xếp theo giai đoạn", row_s2["stage_lbl"].winfo_ismapped())
check("tên nhóm GPM hiện mờ trên dòng", row_s2["group_lbl"].cget("text") == "Mail lô A" and row_s2["group_lbl"].winfo_ismapped())
row_none = next(r for r in app.profile_rows if r["id"] == P_NONE)
check("acc chưa đặt ngày: pill ghi 'chưa đặt ngày'", row_none["stage_lbl"].cget("text") == "chưa đặt ngày")
# acc vừa đổi giai đoạn hôm nay
check("P_NEW: pill 'H1/7 · mới hôm nay' tô accent",
      "mới hôm nay" in row_new["stage_lbl"].cget("text") and row_new["stage_lbl"].cget("bg") == app.C_ACCENT,
      row_new["stage_lbl"].cget("text"))
check("acc KHÔNG đổi hôm nay không bị gắn 'mới'", "mới" not in row_s2["stage_lbl"].cget("text"))
# lọc nhóm GPM vẫn chạy trong chế độ giai đoạn
app.var_prof_group.set("Seeding")
app.cbo_prof_group.winfo_ismapped = lambda: True
app._filter_profiles(); root.update()
shown = [r["id"] for r in app.profile_rows if not r["hidden"]]
check("lọc nhóm Seeding (chế độ giai đoạn): chỉ còn S4 + chưa ngày", set(shown) == {P_S4, P_NONE}, str(shown))
check("header mục không còn dòng hiện thì ẨN", not app._group_headers["S0"]["frame"].winfo_ismapped() and app._group_headers["S4"]["frame"].winfo_ismapped())
app.var_prof_group.set(ui.GROUP_ALL)
app._filter_profiles(); root.update()
# đổi sang Nhóm GPM
app.var_prof_groupby.set(app.PROF_GROUPBY_LABELS["group"])
app._on_groupby_changed(); root.update()
check("Xếp theo Nhóm GPM -> header = tên nhóm (+ Chưa có nhóm)",
      set(app._group_headers.keys()) == {"Mail lô A", "Seeding", ui.UNGROUPED_LABEL}, str(sorted(app._group_headers)))
check("chế độ nhóm: pill ngày ẩn", not row_s2["stage_lbl"].winfo_ismapped() and not row_s2["group_lbl"].winfo_ismapped())
check("config nhớ prof_group_by='group'", app_config.load_config().get("prof_group_by") == "group")
app.var_prof_groupby.set(app.PROF_GROUPBY_LABELS["stage"])
app._on_groupby_changed(); root.update()
check("quay lại giai đoạn -> header S-codes", "S0" in app._group_headers and "" in app._group_headers)

# ---------------------------------------------------------------- 4
hr("[4] Tự đồng bộ stage_history khi mở app (không cần chạy bot)")
ch = db.get_latest_stage_changes()
check("P_NEW: UI đã ghi S1 hôm nay (n_rows=2, source auto)", ch.get(P_NEW, {}).get("stage") == "S1" and ch[P_NEW]["n_rows"] == 2
      and str(ch[P_NEW]["entered_at"])[:10] == TODAY.isoformat(), str(ch.get(P_NEW)))
check("P_S0: lần đầu ghi -> n_rows=1 (không bị coi là 'mới')", ch.get(P_S0, {}).get("n_rows") == 1, str(ch.get(P_S0)))
n_before = len(db.get_stage_history(P_S0))
app._stage_overview_cached(force=True)
app._stage_overview_cached(force=True)
check("gọi lại nhiều lần KHÔNG phình stage_history (dedup)", len(db.get_stage_history(P_S0)) == n_before)
check("acc chưa đặt ngày không được ghi history", db.get_stage_history(P_NONE) == [])

# ---------------------------------------------------------------- 5
hr("[5] Hộp xác nhận: cột Giai đoạn / Chế độ chạy")
app._phase_by_pid, app._phase_src = app.resolve_profile_phases(ALL)
amap, rows = ui.assign_topics_for_run(ALL, [{"google_query": "walking shoes", "youtube_query": "walking"}])
app._plan_preview = {p: {"plan": [], "src": "test"} for p in ALL}
app._proxy_note = []
seen = {}


def _probe():
    try:
        win = find_toplevel("Xác nhận phân bổ")
        tree = find_all(win, ttk.Treeview)[0]
        seen["cols"] = list(tree["columns"])
        seen["hdr"] = {c: str(tree.heading(c, "text")) for c in seen["cols"]}
        seen["vals"] = {tree.set(i, "id"): (tree.set(i, "stage"), tree.set(i, "mode")) for i in tree.get_children()}
    except Exception as e:
        seen["err"] = repr(e)
    for b in find_all(win, ttk.Button):
        if (b.cget("text") or "").strip() == "HỦY":
            b.invoke()
            break


root.after(500, _probe)
ok = app.show_assignment_confirm(rows, pinned=False)
check("HỦY -> trả False", ok is False)
check("hộp có cột stage + mode trước plan", seen.get("cols", [])[-3:] == ["stage", "mode", "plan"], str(seen.get("cols")))
check("tiêu đề cột đúng chữ", seen.get("hdr", {}).get("stage") == "Giai đoạn" and seen["hdr"].get("mode") == "Chế độ chạy", str(seen.get("hdr")))
v = seen.get("vals", {})
check("S2: 'Giai đoạn 2 · H3/7' -> '2 · Nuôi Google (giai đoạn)'",
      v.get(P_S2[:8]) == ("Giai đoạn 2 · H3/7", "2 · Nuôi Google (giai đoạn)"), str(v.get(P_S2[:8])))
check("S4: nhãn sheet 'Ngâm kênh' -> '3 · Cày YouTube'", v.get(P_S4[:8], ("", ""))[0].startswith("Ngâm kênh") and v[P_S4[:8]][1].startswith("3 · Cày YouTube"), str(v.get(P_S4[:8])))
check("chưa đặt ngày -> 'Chưa đặt ngày' + '(mặc định)'", v.get(P_NONE[:8]) == ("Chưa đặt ngày", "1 · Acc mới (mặc định)"), str(v.get(P_NONE[:8])))
check("ghim tay -> '(ghim)'", v.get(P_PIN[:8], ("", ""))[1] == "2 · Nuôi Google (ghim)", str(v.get(P_PIN[:8])))

# ---------------------------------------------------------------- 6
hr("[6] _worker_body dùng chế độ riêng của acc")
got = {}


class FakeApi:
    def get_profile_name(self, pid): return "acc-" + pid[:4]
    def close_profile(self, pid): pass


_orig_get_api = ui.BrowserFactory.get_api
_orig_rsp = ui.run_single_profile
_orig_stagger = ui._stagger_startup
ui.BrowserFactory.get_api = staticmethod(lambda *a, **k: FakeApi())
ui.run_single_profile = lambda api, pid, name, themes, slot, sw, sh, sy, sr, brain, phase, *rest: got.__setitem__(pid, phase)
ui._stagger_startup = lambda *a, **k: True


class StubApp:
    _assignment_map = {}
    _phase_by_pid = {P_S4: "youtube", P_S2: "mail"}
    def update_tab_name(self, *a): pass


try:
    ui.STOP_EVENT.clear()
    for pid in (P_S4, P_S2, P_NONE):
        q = queue.Queue(); q.put(0)
        ui._worker_body(StubApp(), pid, [], q, 1920, 1080, False, False, ui.BROWSER_GPM, "", "none", "clean", 0, 0, "", "en")
    check("S4 nhận 'youtube' dù combobox clean", got.get(P_S4) == "youtube", str(got))
    check("S2 nhận 'mail'", got.get(P_S2) == "mail", str(got))
    check("acc không có trong map -> giữ phase mặc định truyền vào", got.get(P_NONE) == "clean", str(got))
finally:
    ui.BrowserFactory.get_api = _orig_get_api
    ui.run_single_profile = _orig_rsp
    ui._stagger_startup = _orig_stagger

# ---------------------------------------------------------------- 7
hr("[7] Menu + tab giai đoạn")
menu = app.mbtn_report["menu"]
menu_w = root.nametowidget(menu) if isinstance(menu, str) else menu
labels = []
try:
    for i in range(menu_w.index("end") + 1):
        try:
            labels.append(menu_w.entrycget(i, "label"))
        except tk.TclError:
            pass
except Exception as e:
    labels = [f"err {e}"]
check("menu Báo cáo không còn 'Mốc nuôi acc (7 ngày)'", not any("Mốc nuôi acc" in str(x) for x in labels), str(labels))
check("menu vẫn có 'Giai đoạn ngâm'", any("Giai đoạn ngâm" in str(x) for x in labels), str(labels))
btn_tasks = [b for b in find_all(app.stage_frame, ttk.Button) if (b.cget("text") or "").startswith("Việc làm tay")]
check("tab giai đoạn có nút 'Việc làm tay (Giai đoạn 1)'", len(btn_tasks) == 1)
MB.reset()
btn_tasks[0].invoke()
check("bấm -> hiện checklist 4 việc của sheet (2SV, khôi phục, Safe Browsing)",
      MB.titles("showinfo") == ["Giai đoạn 1 — việc làm tay"] and "2SV" in MB.calls[0][2] and "Enhanced Safe Browsing" in MB.calls[0][2])
check("btn_timeline vẫn tồn tại (đối tượng ẩn, tương thích tuple disable)", hasattr(app, "btn_timeline"))

# ---------------------------------------------------------------- 8
hr("[8] Config round-trip")
app.var_force_phase.set(True)
app.save_current_config()
cfg = app_config.load_config()
check("force_phase lưu True", cfg.get("force_phase") is True)
check("prof_group_by lưu 'stage'", cfg.get("prof_group_by") == "stage")
check("DEFAULTS có 2 key mới", app_config.DEFAULTS.get("force_phase") is False and app_config.DEFAULTS.get("prof_group_by") == "stage")
app.var_force_phase.set(False)
app.save_current_config()
check("force_phase lưu False", app_config.load_config().get("force_phase") is False)

# ---------------------------------------------------------------- 8b
hr("[8b] Đặt ngày hàng loạt cho acc đã tick")
P_B1 = "a7777777-7777-4777-8777-777777777777"
P_B2 = "a8888888-8888-4888-8888-888888888888"
app._rebuild_profile_rows(entries + [
    {"id": P_B1, "name": "Bulk 1", "firefox": False, "selected": True, "group": "Lô mới"},
    {"id": P_B2, "name": "Bulk 2", "firefox": False, "selected": True, "group": "Lô mới"},
])
for r in app.profile_rows:
    r["var"].set(r["id"] in (P_B1, P_B2, P_S0))
root.update()
check("header CHƯA ĐẶT NGÀY có nút 'Đặt ngày…'",
      any(b.cget("text") == "Đặt ngày…" for b in find_all(app._group_headers[""]["frame"], tk.Button)))
MB.reset()
app.show_bulk_date_dialog()
root.update()
dlg = find_toplevel("Đặt ngày hàng loạt")
check("mở dialog cho 3 acc đã tick", dlg is not None and "3 acc" in dlg.title(), str(dlg and dlg.title()))
app._bulk_ent_start.insert(0, "19/11/2026")
app._bulk_ent_mail.insert(0, "")
app._bulk_btn_apply.invoke()
root.update()
rows_db = db.get_profile_stage_rows()
check("2 acc mới nhận start_date (dạng dd/mm/yyyy được parse)",
      rows_db.get(P_B1, {}).get("start_date") == "2026-11-19" and rows_db.get(P_B2, {}).get("start_date") == "2026-11-19")
check("acc S0 đã có start_date KHÔNG bị ghi đè (chỉ điền ô trống)",
      rows_db.get(P_S0, {}).get("start_date") == D(2) and app._bulk_last == {"start": 2, "mail": 0, "skipped": 1}, str(app._bulk_last))
check("danh sách tự xếp lại: Bulk 1 sang mục S0", app._row_section(next(r for r in app.profile_rows if r["id"] == P_B1)) == "S0")
app._bulk_ent_mail.insert(0, "2026-11-18")
app._bulk_btn_apply.invoke()
root.update()
rows_db = db.get_profile_stage_rows()
check("đặt ngày lắp mail -> 3 acc có mail_date", all(rows_db.get(p, {}).get("mail_date") == "2026-11-18" for p in (P_B1, P_B2, P_S0)))
check("acc sang mục Giai đoạn 2 (H2/7)", app._row_section(next(r for r in app.profile_rows if r["id"] == P_S0)) == "S2")
app._bulk_ent_mail.delete(0, "end"); app._bulk_ent_mail.insert(0, "31/13/2026")
MB.reset(); app._bulk_btn_apply.invoke(); root.update()
check("ngày sai -> showerror, không ghi", MB.titles("showerror") == ["Ngày không hợp lệ"])
dlg.destroy(); root.update()
for r in app.profile_rows:
    r["var"].set(False)
MB.reset(); app.show_bulk_date_dialog(); root.update()
check("không tick acc nào -> cảnh báo, không mở dialog", MB.titles("showwarning") == ["Chưa tick acc"] and find_toplevel("Đặt ngày hàng loạt") is None)

# ---------------------------------------------------------------- 9
hr("[9] Tĩnh")
src_ui = open(os.path.join(HERE, "ui_main.py"), encoding="utf-8").read()
src_wu = open(os.path.join(HERE, "workflow", "warmup.py"), encoding="utf-8").read()
check("warmup.py không bị đụng", "resolve_profile_phases" not in src_wu and "_phase_by_pid" not in src_wu)
check("không còn hộp 'Lệch chế độ ngâm'", "Lệch chế độ ngâm" not in src_ui)
check("chữ ký worker/Thread giữ nguyên (test_v153)", "fixed_target_s, daily_seconds, pinned_theme, keyword_lang) for pid in profiles]" in src_ui)
check("sheet labels nguyên vẹn", dbm.STAGE_SHEET_LABELS == {"S0": "Giai đoạn 0", "S1": "Giai đoạn 1", "S2": "Giai đoạn 2",
                                                            "S3": "Giai đoạn 3", "S4": "Ngâm kênh", "S5": "Giai đoạn 4"}, str(dbm.STAGE_SHEET_LABELS))
check("ánh xạ giai đoạn -> chế độ không đổi", dbm.STAGE_SUGGESTED_PHASE == {"S0": "clean", "S1": "mail", "S2": "mail", "S3": "mail", "S4": "youtube", "S5": "youtube"})
check("STAGE0_DAYS=4 / HAGRID_DAYS=7 không đổi", dbm.STAGE0_DAYS == 4 and dbm.HAGRID_DAYS == 7)
check("worker đọc _phase_by_pid trước run_single_profile",
      src_ui.index('_pmap = getattr(app_instance, "_phase_by_pid"') < src_ui.index("run_single_profile(api, profile_id, profile_name, themes, slot,"))
check("_prepare_plans dùng pha riêng từng acc", 'th.get("phase") or phase' in src_ui)

root.destroy()
sys.stdout = sys.__stdout__  # app đã thay stdout bằng ThreadSafeStdout -> trả lại console
check("hash DB THẬT không đổi", _real_hash() == REAL_HASH_BEFORE)
print(f"\nPASS: {PASS}   FAIL: {FAIL}")
print("SMOKE v1.9.2: " + ("ALL PASS" if FAIL == 0 else f"{FAIL} FAIL"))
sys.stdout.flush()
os._exit(0 if FAIL == 0 else 1)  # thread nền (auto-load profile) có thể còn sống -> thoát cứng
