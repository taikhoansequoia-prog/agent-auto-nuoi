# -*- coding: utf-8 -*-
"""
Smoke test v1.5.0 — GIAI ĐOẠN NGÂM S0..S5 (DB engine + tab UI + dialog chi tiết + backfill).

Chạy:  python test_v150.py
Cô lập: GPM_BOT_DATA_DIR -> temp dir (KHÔNG đụng data thật của user).

Phủ:
  [1] compute_stage hai đồng hồ D/H + mọi trường biên (mail quá khứ, tương lai, không ngày)
  [2] suggested_phase + STAGE_* constants + _parse_iso_date
  [3] schema mới (profile_timeline 4 cột, stage_history, index) + setter giữ cột anh-em
  [4] set_profile_stage_meta: ghim pha hợp lệ/bỏ giá trị rác, niche, note, clear_fields
  [5] log_stage_change dedup + get_stage_history append-only
  [6] get_stage_overview: clock A/B, phase ép, bằng chứng, sinh cảnh báo
  [7] backfill_stage_tracking: điền start từ activity, gợi ý mail KHÔNG tự ghi, idempotent
  [8] Tab "GIAI ĐOẠN NGÂM": 13 cột, bộ lọc giai đoạn, "chỉ hiện cảnh báo", sắp xếp, status
  [9] Cột "Giai đoạn" trên bảng THỜI LƯỢNG CHẠY đọc từ cùng 1 cache (1 truy vấn dùng chung)
  [10] Dialog chi tiết giai đoạn: đặt ngày hôm nay / ghim pha / ghi chú / ghi mốc -> DB thật
  [11] Backfill qua UI: dialog kết quả + nút "Dùng" ghi mail_date
  [12] Nút "GIAI ĐOẠN NGÂM" (btn_stage) điều hướng tới tab cuối + invalidate cache
  [13] start_automation: tab giai đoạn tạo SAU tab board, không nhân đôi; cảnh báo lệch pha
  [14] Kiểm tra tĩnh: warmup.py không bị đụng, hàm mới có đủ wiring
"""
import hashlib
import os
import re
import sqlite3
import sys
import tempfile
import time
import datetime as dt
import tkinter as tk
import tkinter.messagebox as mb_real
import tkinter.simpledialog as sd_real
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

TMP = tempfile.mkdtemp(prefix="gpm_v150_")
DATA_DIR = os.path.join(TMP, "data")
os.makedirs(DATA_DIR, exist_ok=True)

REAL_DB = os.path.join(REPO, "data", "agent_logs.db")

# Alias: test tự gọi messagebox thật ở vài chỗ (restore ui.messagebox = MB cho recorder)
messagebox = mb_real


def _real_hash():
    try:
        return hashlib.sha256(open(REAL_DB, "rb").read()).hexdigest()
    except Exception:
        return None


REAL_HASH_BEFORE = _real_hash()
os.environ["GPM_BOT_DATA_DIR"] = DATA_DIR   # PHẢI đặt trước khi import db_handler

from src.database.db_handler import DatabaseHandler  # noqa: E402
from src.database import db_handler as dbm  # noqa: E402

PASS, FAIL = 0, 0


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


class _MsgBox:
    """Recorder thay cho tkinter.messagebox. QUAN TRỌNG: mọi hàm messagebox là
    BLOCKING (grab + chờ người bấm) nên test PHẢI thay chúng bằng recorder,
    nếu không suite treo ở dialog đầu tiên."""

    def __init__(self):
        self.calls = []
        self.yes = True

    def _rec(self, kind, title, message, **kw):
        self.calls.append((kind, str(title), str(message)))
        return self.yes if kind.startswith("ask") else None

    def showwarning(self, t, m, **k):
        return self._rec("showwarning", t, m)

    def showerror(self, t, m, **k):
        return self._rec("showerror", t, m)

    def showinfo(self, t, m, **k):
        return self._rec("showinfo", t, m)

    def askyesno(self, t, m, **k):
        return self._rec("askyesno", t, m)

    def askokcancel(self, t, m, **k):
        return self._rec("askokcancel", t, m)

    def titles(self, kind=None):
        return [t for (k, t, m) in self.calls if kind is None or k == kind]

    def messages(self, kind=None):
        return [m for (k, t, m) in self.calls if kind is None or k == kind]

    def last(self, kind=None):
        for c in reversed(self.calls):
            if kind is None or c[0] == kind:
                return c
        return None

    def reset(self):
        self.calls = []


MB = _MsgBox()


def sum_values_of(frame):
    """Đọc khối tóm tắt của dialog giai đoạn: sản phẩm KHÔNG giữ tham chiếu label
    giá trị (chỉ nằm trong closure `vals`), nên phải ghép theo hàng grid:
    col 0 = nhãn 'Xxx:', col 1 = giá trị -> {'Xxx': text}."""
    out = {}
    for k in frame.winfo_children():
        if not isinstance(k, tk.Label):
            continue
        try:
            gi = k.grid_info()
            row = int(gi.get("row", -1))
        except (ValueError, tk.TclError):
            continue
        if row < 0:
            continue
        out.setdefault(row, {})[str(gi.get("column"))] = k
    res = {}
    for _row, cols in out.items():
        lab, val = cols.get("0"), cols.get("1")
        if lab is None or val is None:
            continue
        res[str(lab.cget("text")).rstrip(":")] = str(val.cget("text"))
    return res


def find_toplevel(title_fragment):
    """Tìm Toplevel đang mở theo fragment tiêu đề.
    LƯU Ý: Python 3.14 KHÔNG có class attribute `tk.Toplevel._default_root`
    (AttributeError) -> phải duyệt từ root Tk thật (biến toàn cục `root`, tạo ở [8]).
    Quét ĐỆ QUY vì dialog con (kết quả backfill) có thể là con của dialog cha."""
    out = []

    def _walk(w):
        for c in w.winfo_children():
            if isinstance(c, tk.Toplevel):
                try:
                    if title_fragment in (c.title() or ""):
                        out.append(c)
                except Exception:
                    pass
            _walk(c)

    _walk(root)
    return out[-1] if out else None


def click_btn(win, text):
    for b in find_all(win, tk_btn := __import__("tkinter", fromlist=["ttk"]).ttk.Button):
        if (b.cget("text") or "").strip().startswith(text):
            b.invoke()
            return True
    return False


_TODAY = dt.date.today()
_YEST = _TODAY - dt.timedelta(days=1)
_FUT = _TODAY + dt.timedelta(days=3)
_OLD = _TODAY - dt.timedelta(days=10)

db = DatabaseHandler()

# ---------------------------------------------------------------- 1. compute_stage
hr("[1] compute_stage — hai đồng hồ D (chưa mail) / H (Hagrid đã mail)")
check("hằng số STAGE0_DAYS=4 / HAGRID_DAYS=7",
      dbm.STAGE0_DAYS == 4 and dbm.HAGRID_DAYS == 7)
check("STAGE_CODES = S0..S5", dbm.STAGE_CODES == ["S0", "S1", "S2", "S3", "S4", "S5"],
      str(dbm.STAGE_CODES))

# Đồng hồ A: chưa có mail -> S0 trong 4 ngày
a0 = dbm.compute_stage(_TODAY.isoformat(), None, _TODAY)
check("A ngày 0 -> S0 D1/4", a0["stage"] == "S0" and a0["clock"] == "A"
      and a0["day_label"] == "D1/4" and a0["day_no"] == 1, str(a0))
a3 = dbm.compute_stage((_TODAY - dt.timedelta(days=3)).isoformat(), "", _TODAY)
check("A ngày 3 -> S0 D4/4 còn 1 ngày", a3["stage"] == "S0" and a3["day_label"] == "D4/4"
      and a3["days_left"] == 1 and a3["overdue"] is False, str(a3))
a9 = dbm.compute_stage((_TODAY - dt.timedelta(days=9)).isoformat(), None, _TODAY)
check("A ngày 9 (chưa mail) -> vẫn S0 + overdue", a9["stage"] == "S0" and a9["overdue"] is True
      and a9["day_label"] == "D10/4", str(a9))

# Đồng hồ B: có mail -> tính theo Hagrid, mail date = ngày 1
b = dbm.compute_stage(_OLD.isoformat(), _TODAY.isoformat(), _TODAY)
check("B offset 0 -> S1 H1/7", b["stage"] == "S1" and b["clock"] == "B"
      and b["day_label"] == "H1/7" and b["days_left"] == 6, str(b))
for off, want in ((1, "S2"), (3, "S2"), (4, "S3"), (5, "S4"), (6, "S5"), (8, "S5")):
    mail = _TODAY - dt.timedelta(days=off)
    r = dbm.compute_stage(_OLD.isoformat(), mail.isoformat(), _TODAY)
    check(f"B offset {off} -> {want}", r["stage"] == want, f"got {r['stage']} {r['day_label']}")
check("B offset 5 -> S4 tên giai đoạn 'Ngâm kênh'",
      dbm.compute_stage(_OLD.isoformat(), (_TODAY - dt.timedelta(days=5)).isoformat(),
                        _TODAY)["stage_name"] == "Ngâm kênh")
check("B offset 8 -> nhãn sheet 'Giai đoạn 4'",
      dbm.compute_stage(_OLD.isoformat(), (_TODAY - dt.timedelta(days=8)).isoformat(),
                        _TODAY)["sheet_label"] == "Giai đoạn 4")
bf = dbm.compute_stage(_OLD.isoformat(), _FUT.isoformat(), _TODAY)
check("B mail tương lai -> S1 + overdue (coi như mới)", bf["stage"] == "S1" and bf["overdue"] is True,
      str(bf))
bbig = dbm.compute_stage(_OLD.isoformat(), (_TODAY - dt.timedelta(days=200)).isoformat(), _TODAY)
check("B offset 200 -> S5 H201/7", bbig["stage"] == "S5" and bbig["day_label"] == "H201/7",
      str(bbig))

# Không ngày / ngày tương lai
n0 = dbm.compute_stage(None, None, _TODAY)
check("không ngày -> stage rỗng", n0["stage"] == "" and n0["clock"] == ""
      and n0["day_label"] == "", str(n0))
n1 = dbm.compute_stage(_FUT.isoformat(), None, _TODAY)
check("start tương lai -> stage rỗng", n1["stage"] == "", str(n1))
n2 = dbm.compute_stage("rac", "rac", _TODAY)
check("ngày rác -> stage rỗng (không nổ)", n2["stage"] == "", str(n2))
check("STAGE_NAMES đủ 6 mã", set(dbm.STAGE_NAMES) == set(dbm.STAGE_CODES))

# ---------------------------------------------------------------- 2. suggested_phase
hr("[2] suggested_phase + _parse_iso_date")
check("S0 -> clean", dbm.suggested_phase("S0") == "clean")
check("S1/S2/S3 -> mail", all(dbm.suggested_phase(s) == "mail" for s in ("S1", "S2", "S3")))
check("S4/S5 -> youtube", dbm.suggested_phase("S4") == "youtube"
      and dbm.suggested_phase("S5") == "youtube")
check("mã lạ/rỗng -> clean", dbm.suggested_phase("XX") == "clean" and dbm.suggested_phase("") == "clean")
check("_parse_iso_date hợp lệ", dbm._parse_iso_date("2026-10-01") == dt.date(2026, 10, 1))
check("_parse_iso_date rác/None -> None",
      dbm._parse_iso_date("abc") is None and dbm._parse_iso_date(None) is None
      and dbm._parse_iso_date("") is None)
check("VALID_PHASES = clean/mail/youtube", dbm.VALID_PHASES == ("clean", "mail", "youtube"))

# ---------------------------------------------------------------- 3. schema + setters
hr("[3] schema mới + setter giữ cột anh-em")
conn = sqlite3.connect(db.db_path)
cols = {r[1] for r in conn.execute("PRAGMA table_info(profile_timeline)")}
check("profile_timeline có mail_date/phase_override/niche/note",
      {"mail_date", "phase_override", "niche", "note"} <= cols, str(sorted(cols)))
tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
check("bảng stage_history tồn tại", "stage_history" in tables, str(sorted(tables)))
scols = {r[1] for r in conn.execute("PRAGMA table_info(stage_history)")}
check("stage_history đủ cột id/profile_id/stage/entered_at/source/note",
      {"id", "profile_id", "stage", "entered_at", "source", "note"} <= scols, str(sorted(scols)))
idx = {r[1] for r in conn.execute("PRAGMA index_list(stage_history)")}
check("index idx_stage_history_profile", "idx_stage_history_profile" in idx, str(idx))
conn.close()

PID_S = "PID-STAGE-S"
check("set_profile_start_date trả True", db.set_profile_start_date(PID_S, _OLD.isoformat()) is True)
check("set_profile_mail_date giữ được start_date",
      (db.set_profile_mail_date(PID_S, _YEST.isoformat()) is True)
      and db.get_profile_stage_rows()[PID_S]["start_date"] == _OLD.isoformat(),
      str(db.get_profile_stage_rows().get(PID_S)))
check("set_profile_start_date KHÔNG xoá mail_date",
      db.set_profile_start_date(PID_S, _OLD.isoformat()) is True
      and db.get_profile_stage_rows()[PID_S]["mail_date"] == _YEST.isoformat())
check("set_profile_mail_date('') xoá mail nhưng giữ start",
      db.set_profile_mail_date(PID_S, "") is True
      and db.get_profile_stage_rows()[PID_S]["mail_date"] == ""
      and db.get_profile_stage_rows()[PID_S]["start_date"] == _OLD.isoformat())
check("get_profile_stage_rows pid chưa biết -> không có key",
      PID_S in db.get_profile_stage_rows())

# ---------------------------------------------------------------- 4. meta
hr("[4] set_profile_stage_meta — ghim pha / niche / note / clear_fields")
check("ghim phase_override=mail", db.set_profile_stage_meta(PID_S, phase_override="mail") is True
      and db.get_profile_stage_rows()[PID_S]["phase_override"] == "mail")
check("giá trị pha rác bị bỏ qua (giữ mail)",
      db.set_profile_stage_meta(PID_S, phase_override="khong-co-that") is True
      and db.get_profile_stage_rows()[PID_S]["phase_override"] == "mail")
check("niche lưu được", db.set_profile_stage_meta(PID_S, niche="ve gia re") is True
      and db.get_profile_stage_rows()[PID_S]["niche"] == "ve gia re")
check("note lưu được", db.set_profile_stage_meta(PID_S, note="acc lô 2") is True
      and db.get_profile_stage_rows()[PID_S]["note"] == "acc lô 2")
check("clear_fields xoá đúng pha + note (giữ niche)",
      db.set_profile_stage_meta(PID_S, clear_fields=("phase_override", "note")) is True
      and db.get_profile_stage_rows()[PID_S]["phase_override"] == ""
      and db.get_profile_stage_rows()[PID_S]["niche"] == "ve gia re")
check("tạo dòng cho profile hoàn toàn mới",
      db.set_profile_stage_meta("PID-META-NEW", niche="moi") is True
      and db.get_profile_stage_rows()["PID-META-NEW"]["niche"] == "moi")
check("pid rỗng -> True (best-effort, không nổ)", db.set_profile_stage_meta("", niche="x") is True)

# ---------------------------------------------------------------- 5. stage_history
hr("[5] log_stage_change dedup + sổ append-only")
PID_H = "PID-HIST"
db.set_profile_start_date(PID_H, _OLD.isoformat())
check("ghi S1 lần đầu -> True", db.log_stage_change(PID_H, "S1", source="auto") is True)
check("ghi S1 lặp lại -> False (chống rác)", db.log_stage_change(PID_H, "S1", source="auto") is False)
check("ghi S2 -> True", db.log_stage_change(PID_H, "S2", source="manual", note="tay") is True)
h = db.get_stage_history(PID_H)
check("history mới nhất trước, đủ 2 dòng", len(h) == 2 and h[0]["stage"] == "S2"
      and h[1]["stage"] == "S1", str(h))
check("source + note lưu đúng", h[0]["source"] == "manual" and h[0]["note"] == "tay"
      and h[1]["source"] == "auto")
check("stage rỗng -> False", db.log_stage_change(PID_H, "") is False)
check("pid rỗng -> False", db.log_stage_change("", "S1") is False)
check("pid chưa có dòng -> history rỗng", db.get_stage_history("PID-KHONG-CO") == [])

# ---------------------------------------------------------------- 6. overview
hr("[6] get_stage_overview — ghép 2 đồng hồ + bằng chứng + cảnh báo")
PID_O = "PID-OVER"
db.set_profile_start_date(PID_O, (_TODAY - dt.timedelta(days=12)).isoformat())
db.set_profile_mail_date(PID_O, (_TODAY - dt.timedelta(days=5)).isoformat())  # offset 5 -> S4
ov = db.get_stage_overview(today=_TODAY)
check("overview là dict theo pid", isinstance(ov, dict) and PID_O in ov, str(list(ov))[:120])
i = ov.get(PID_O, {})
check("S4 + effective_phase youtube", i.get("stage") == "S4" and i.get("effective_phase") == "youtube"
      and i.get("phase_forced") is False,
      str({k: i.get(k) for k in ("stage", "effective_phase", "phase_forced")}))
check("overview kèm warnings(list) + evidence(dict)",
      isinstance(i.get("warnings"), list) and isinstance(i.get("evidence"), dict))
check("S4 chưa có YouTube -> có cảnh báo youtube",
      any("YouTube" in w for w in i.get("warnings", [])), str(i.get("warnings")))
# ghim pha -> effective đổi, phase_forced True
db.set_profile_stage_meta(PID_O, phase_override="clean")
ov2 = db.get_stage_overview(today=_TODAY)
check("ghim clean -> effective_phase clean + phase_forced True",
      ov2[PID_O]["effective_phase"] == "clean" and ov2[PID_O]["phase_forced"] is True)
# profile chỉ có start, chưa mail, chờ >7 ngày -> cảnh báo kẹt S0
PID_K = "PID-KET"
db.set_profile_start_date(PID_K, (_TODAY - dt.timedelta(days=15)).isoformat())
ov3 = db.get_stage_overview(today=_TODAY)
check("kẹt S0 >7 ngày -> cảnh báo 'kẹt ở S0'",
      ov3[PID_K]["stage"] == "S0" and any("kẹt" in w for w in ov3[PID_K]["warnings"]),
      str(ov3[PID_K]["warnings"]))
# profile không ngày (tạo dòng rỗng bằng meta niche) -> cảnh báo chưa đặt ngày
PID_N = "PID-NODATE"
db.set_profile_stage_meta(PID_N, niche="khong ngay")
ov4 = db.get_stage_overview(today=_TODAY)
check("không ngày -> stage rỗng + cảnh báo 'chưa đặt ngày'",
      ov4[PID_N]["stage"] == "" and any("chưa đặt ngày" in w for w in ov4[PID_N]["warnings"]),
      str(ov4[PID_N]["warnings"]))
# evidence: activity + alert + youtube
PID_E = "PID-EVID"
db.set_profile_start_date(PID_E, (_TODAY - dt.timedelta(days=10)).isoformat())
db.set_profile_mail_date(PID_E, (_TODAY - dt.timedelta(days=8)).isoformat())  # S5
db.log_activity(PID_E, "watch_video", "YouTube", "https://youtu.be/x", "video nua")
DatabaseHandler().log_alert_created(PID_E, "ve gia re")
ov5 = db.get_stage_overview(today=_TODAY)
ev = ov5[PID_E]["evidence"]
# LƯU Ý sản phẩm: evidence["last_action"] = MAX(created_at) (dấu thời gian), KHÔNG phải
# tên hành động (db_handler L860-861 gán cùng giá trị với last_activity) -> test bắt buộc
# là chuỗi thời gian không rỗng, không được so với tên action.
check("evidence has_alert + has_yt + last_action là dấu thời gian",
      ev.get("has_alert") is True and ev.get("has_yt") is True
      and bool(ev.get("last_action")) and ev["last_action"][:10] == _TODAY.isoformat()
      and ev.get("last_action") == ev.get("last_activity"), str(ev))
check("S5 có đủ bằng chứng -> không còn cảnh báo YouTube",
      not any("YouTube" in w for w in ov5[PID_E]["warnings"]), str(ov5[PID_E]["warnings"]))
check("day_total = 7 khi đồng hồ B", ov5[PID_E]["day_total"] == 7, str(ov5[PID_E].get("day_total")))

# ---------------------------------------------------------------- 7. backfill
hr("[7] backfill_stage_tracking")
PID_B1 = "PID-BACKFILL-1"   # có activity, chưa có gì -> điền start + log stage
PID_B2 = "PID-BACKFILL-2"   # có alert -> chỉ gợi ý mail, không tự ghi
PID_B3 = "PID-BACKFILL-3"   # đã có start tay -> không được ghi đè
conn = sqlite3.connect(db.db_path)
# Định dạng GIỐNG SẢN PHẨM (log_activity ghi `datetime.now().isoformat(timespec="seconds")`
# = phân tách bằng CHỮ T). date.isoformat() KHÔNG nhận timespec -> phải qua datetime.
def _ts(day, hh=12, mm=0):
    return dt.datetime(day.year, day.month, day.day, hh, mm).isoformat(timespec="seconds")


conn.execute("INSERT INTO activity_history (profile_id, action, platform, url, title, created_at) "
             "VALUES (?,?,?,?,?,?)", (PID_B1, "read_news", "bbc.com", "https://bbc.com", "t",
                                      _ts(_TODAY - dt.timedelta(days=6))))
conn.execute("INSERT INTO alert_history (profile_id, query, created_at) VALUES (?,?,?)",
             (PID_B2, "ve gia re", _ts(_TODAY - dt.timedelta(days=2))))
conn.execute("INSERT INTO activity_history (profile_id, action, platform, url, title, created_at) "
             "VALUES (?,?,?,?,?,?)", (PID_B2, "search_youtube", "YouTube", "https://youtube.com",
                                      "u", _ts(_TODAY - dt.timedelta(days=9))))
conn.execute("INSERT INTO profile_timeline (profile_id, start_date) VALUES (?,?)",
             (PID_B3, (_TODAY - dt.timedelta(days=40)).isoformat()))
conn.commit()
conn.close()
res = db.backfill_stage_tracking()
check("backfill trả dict đủ 3 khoá", set(res) == {"filled_start", "logged", "mail_hints"}, str(res))
check("start B1 điền từ activity (MIN date)",
      db.get_profile_stage_rows()[PID_B1]["start_date"]
      == (_TODAY - dt.timedelta(days=6)).isoformat(),
      str(db.get_profile_stage_rows()[PID_B1]))
check("start B3 (nhập tay) KHÔNG bị ghi đè",
      db.get_profile_stage_rows()[PID_B3]["start_date"]
      == (_TODAY - dt.timedelta(days=40)).isoformat())
check("mail B2 CHƯA tự ghi (chỉ gợi ý)",
      db.get_profile_stage_rows()[PID_B2]["mail_date"] == "")
check("gợi ý mail đúng ngày alert đầu",
      res["mail_hints"].get(PID_B2) == (_TODAY - dt.timedelta(days=2)).isoformat(),
      str(res["mail_hints"]))
check("backfill ghi stage_history source=backfill",
      any(r["source"] == "backfill" for r in db.get_stage_history(PID_B1)),
      str(db.get_stage_history(PID_B1)))
res2 = db.backfill_stage_tracking()
check("backfill idempotent (lần 2 không điền thêm start)", res2["filled_start"] == 0, str(res2))

# ---------------------------------------------------------------- GUI
hr("[8] Tab GIAI ĐOẠN NGÂM trong GUI")
import ui_main as ui  # noqa: E402

# Sản phẩm gọi messagebox qua `messagebox.xxx` (module-level import trong ui_main)
# -> patch TÊN trong namespace ui_main. simpledialog import trong thân hàm
# -> patch trực tiếp module tkinter.simpledialog.
ui.messagebox = MB
sd_real.askstring = lambda *a, **k: None

root = tk.Tk()
root.withdraw()
app = ui.AutomationApp(root)
root.update()

nb = app.notebook
tab_texts = [str(nb.tab(t, "text") or "").strip() for t in nb.tabs()]
# v1.5.7: tab PHÂN BỔ CHỦ ĐỀ nối SAU giai đoạn -> cuối cùng; giai đoạn áp chót.
check("tab cuối là PHÂN BỔ CHỦ ĐỀ", tab_texts[-1] == "PHÂN BỔ CHỦ ĐỀ", str(tab_texts))
check("tab áp chót là GIAI ĐOẠN NGÂM", tab_texts[-2] == "GIAI ĐOẠN NGÂM", str(tab_texts))
check("tab giai đoạn là con của notebook", app.stage_frame in nb.winfo_children())

t = app.stage_tree
check("đủ 13 cột giai đoạn", list(t["columns"]) == list(app.STAGE_COLUMNS), str(t["columns"]))
check("không có cột #all", "#all" not in t["columns"])
hdrs = [str(t.heading(c, "text") or "").strip() for c in t["columns"]]
check("tiêu đề không emoji (bắt đầu bằng chữ)", hdrs[0].startswith("Tài khoản"), str(hdrs[:3]))
check("cột lọc chỉ số", app.STAGE_NUM_COLS == ("left",))

# Bộ dữ liệu deterministic cho GUI. PROFILE ID PHẢI ĐÚNG ĐỊNH DẠNG UUID vì
# start_automation có cổng validate regex (L3280) trước khi tới khối lệch pha.
PID_G1 = "11111111-1111-4111-8111-111111111111"  # S0 kẹt (không mail, start 12 ngày)
PID_G2 = "22222222-2222-4222-8222-222222222222"  # S4 (mail offset 5)
PID_G3 = "33333333-3333-4333-8333-333333333333"  # chưa xác định (không ngày)
PID_G4 = "44444444-4444-4444-8444-444444444444"  # S5 ép pha clean
db.set_profile_start_date(PID_G1, (_TODAY - dt.timedelta(days=12)).isoformat())
db.set_profile_start_date(PID_G2, (_TODAY - dt.timedelta(days=12)).isoformat())
db.set_profile_mail_date(PID_G2, (_TODAY - dt.timedelta(days=5)).isoformat())
db.set_profile_stage_meta(PID_G3, niche="an choi")
db.set_profile_start_date(PID_G4, (_TODAY - dt.timedelta(days=20)).isoformat())
db.set_profile_mail_date(PID_G4, (_TODAY - dt.timedelta(days=9)).isoformat())
db.set_profile_stage_meta(PID_G4, phase_override="clean")
db.log_activity(PID_G2, "search_youtube", "YouTube", "https://youtube.com", "video")

app.profile_rows = [
    {"id": PID_G1, "name": "Acc S0 keo", "firefox": False, "group": "Nhóm A",
     "hidden": False, "var": tk.BooleanVar(value=True), "frame": None},
    {"id": PID_G2, "name": "Acc S4 da mail", "firefox": False, "group": "Nhóm A",
     "hidden": False, "var": tk.BooleanVar(value=True), "frame": None},
    {"id": PID_G3, "name": "Acc chua dat ngay", "firefox": False, "group": "Nhóm B",
     "hidden": False, "var": tk.BooleanVar(value=True), "frame": None},
    {"id": PID_G4, "name": "Acc S5 ep clean", "firefox": False, "group": "Nhóm B",
     "hidden": False, "var": tk.BooleanVar(value=True), "frame": None},
]
app._stage_cache = None
app._stage_cache_at = 0
app._stage_refresh(force=True)
root.update()

rows = list(t.get_children())
by_pid = {v["pid"]: iid for iid, v in app._stage_raw.items()}
gui_ids = {PID_G1, PID_G2, PID_G3, PID_G4}
check("4 profile GUI đều có dòng", gui_ids <= set(by_pid), str(sorted(set(by_pid))))
check("profile chỉ có ở DB (không ở checklist) vẫn lên bảng",
      PID_O in by_pid or PID_E in by_pid)
check("số dòng == số pid trong _stage_raw", len(rows) == len(app._stage_raw),
      f"{len(rows)} vs {len(app._stage_raw)}")

iid1, iid2, iid3, iid4 = by_pid[PID_G1], by_pid[PID_G2], by_pid[PID_G3], by_pid[PID_G4]
check("dòng S0: stage 'S0 · ...' + clock D13/4",
      t.set(iid1, "stage").startswith("S0") and t.set(iid1, "clock") == "D13/4",
      f"{t.set(iid1,'stage')} | {t.set(iid1,'clock')}")
check("dòng S4: clock H6/7 + pha đề xuất 3 (youtube)",
      t.set(iid2, "clock") == "H6/7" and t.set(iid2, "sug").startswith("3"),
      f"{t.set(iid2,'clock')} | {t.set(iid2,'sug')}")
check("dòng chưa ngày: stage rỗng + cảnh báo 'chưa đặt'",
      t.set(iid3, "stage") == "" and "chưa đặt" in t.set(iid3, "warn"),
      f"[{t.set(iid3,'stage')}] {t.set(iid3,'warn')}")
check("dòng ép pha: sug có '(ép)'", "(ép)" in t.set(iid4, "sug"), t.set(iid4, "sug"))
check("dòng ép pha: stage S5", t.set(iid4, "stage").startswith("S5"))
check("bằng chứng dòng S4 có YouTube", "YouTube" in t.set(iid2, "evid"), t.set(iid2, "evid"))
check("nhóm hiển thị đúng", t.set(iid1, "group") == "Nhóm A" and t.set(iid3, "group") == "Nhóm B")
check("ID cắt 8 ký tự", t.set(iid1, "id") == PID_G1[:8])
check("tên cắt 42 ký tự", len(t.set(iid2, "name")) <= 42)
check("_stage_raw lưu left theo số", isinstance(app._stage_raw[iid1]["left"], (int, float))
      or app._stage_raw[iid1]["left"] is None)
check("dòng S0 có left là số", isinstance(app._stage_raw[iid1]["left"], (int, float)),
      str(app._stage_raw[iid1]))
check("dòng chưa ngày left rỗng (None trong raw)", app._stage_raw[iid3]["left"] is None
      and t.set(iid3, "left") == "")
st = app._stage_status.cget("text")
check("status có tổng số dòng", st.startswith(f"{len(rows)} profile"), st)
check("status đếm theo giai đoạn (có S0)", " S0 " in f" {st} " or "S0" in st, st)
check("status có số cảnh báo", "cảnh báo" in st, st)

# Bộ lọc giai đoạn
app.var_stage_filter.set("S0")
app._stage_refresh()
root.update()
shown = set(t.get_children())
check("lọc S0 -> chỉ còn dòng S0",
      shown and all(app._stage_raw[i]["stage"].startswith("S0") for i in shown), str(shown))
check("status báo số dòng bị ẩn", "bị ẩn bởi bộ lọc" in app._stage_status.cget("text"),
      app._stage_status.cget("text"))
app.var_stage_filter.set(app.STAGE_FILTER_NONE)
app._stage_refresh()
root.update()
check("lọc 'Chưa xác định' -> chỉ dòng không stage",
      set(t.get_children()) == {iid3} or (t.get_children() and all(
          app._stage_raw[i]["stage"] == "" for i in t.get_children())),
      str([(i, app._stage_raw[i]["stage"]) for i in t.get_children()]))
app.var_stage_filter.set(app.STAGE_FILTER_ALL)
app.var_stage_warn.set(True)
app._stage_refresh()
root.update()
check("chỉ hiện cảnh báo -> mọi dòng còn có warn",
      all((t.set(i, "warn") or "") != "" for i in t.get_children()) and t.get_children(),
      str([(t.set(i, 'name'), t.set(i, 'warn')) for i in t.get_children()]))
check("status vẫn tính đủ (n_hidden tăng)", "bị ẩn bởi bộ lọc" in app._stage_status.cget("text"))
app.var_stage_warn.set(False)
app._stage_refresh()
root.update()
check("tắt filter -> trở lại đủ dòng", len(t.get_children()) == len(app._stage_raw))

# Sắp xếp — theo docstring L1604-1606: CLICK ĐẦU TIÊN cột SỐ = giảm dần (▼),
# cột chữ = tăng dần (▲); ô None luôn CUỐI.
raw = t.heading("left")
cmd = raw.get("command")
t.tk.call(cmd)
root.update()
order = [app._stage_raw[i]["left"] for i in t.get_children()]
have = [v for v in order if v is not None]
check("bấm ĐẦU TIÊN 'Còn lại' (cột số) = GIẢM dần",
      have == sorted(have, reverse=True), str(order))
check("None xuống cuối", order[-1] is None or all(v is not None for v in order), str(order))
check("mũi tên ▼ ở đúng cột left", "▼" in str(t.heading("left", "text")),
      str(t.heading("left", "text")))
t.tk.call(cmd)
root.update()
order2 = [app._stage_raw[i]["left"] for i in t.get_children()]
check("bấm lần 2 = TĂNG dần", [v for v in order2 if v is not None]
      == sorted([v for v in order2 if v is not None]), str(order2))
check("mũi tên ▲ sau lần 2", "▲" in str(t.heading("left", "text")))
arrows = [c for c in t["columns"] if "▲" in str(t.heading(c, "text"))
          or "▼" in str(t.heading(c, "text"))]
check("chỉ 1 cột mang mũi tên", len(arrows) == 1, str(arrows))
t.tk.call(t.heading("name").get("command"))
root.update()
names = [t.set(i, "name") for i in t.get_children()]
check("sort chuỗi name hoạt động", names == sorted(names, key=str.lower), str(names))

# ---------------------------------------------------------------- 9. board dùng chung cache
hr("[9] Cột 'Giai đoạn' trên bảng THỜI LƯỢNG CHẠY")
bt = app.board_tree
check("board có 15 cột với stage ở vị trí 3",
      list(bt["columns"])[:3] == ["name", "group", "stage"], str(bt["columns"]))
db.log_cycle(PID_G2, f"{_YEST.isoformat()}T09:00:00", f"{_YEST.isoformat()}T09:10:00",
             600.0, "ok", actions=2, phase="mail", target_s=900)
app._stage_cache = None
app._stage_cache_at = 0
calls = {"n": 0}
_orig_overview = app._stage_overview_cached


def _counting(force=False, **kw):
    calls["n"] += 1
    return _orig_overview(force=force, **kw)


app._stage_overview_cached = _counting
try:
    app._board_refresh()
    root.update()
finally:
    app._stage_overview_cached = _orig_overview
# đọc lại dòng board theo pid
board_stage = ""
for iid in bt.get_children():
    if bt.set(iid, "id") == PID_G2[:8]:
        board_stage = bt.set(iid, "stage")
check("board hiển thị giai đoạn S4 cho acc đã có mail (offset 5)",
      board_stage.startswith("S4"), f"[{board_stage}]")
check("board gọi đúng 1 lần nguồn dữ liệu giai đoạn (cache dùng chung)",
      calls["n"] == 1, str(calls))

# ---------------------------------------------------------------- 10. dialog chi tiết
hr("[10] Dialog chi tiết giai đoạn (show_stage_detail)")
app._stage_cache = None
app._stage_cache_at = 0
PID_D = "PID-DETAIL"
db.set_profile_start_date(PID_D, (_TODAY - dt.timedelta(days=12)).isoformat())
app.profile_rows.append({"id": PID_D, "name": "Acc dialog", "firefox": False,
                         "group": "Nhóm C", "hidden": False, "var": None, "frame": None})
app._stage_refresh(force=True)
root.update()
askstring_real = sd_real.askstring
sd_real.askstring = lambda *a, **k: None      # không nhập tay trong test
# Dialog cha của messagebox ở đây là Toplevel đang mở -> dùng recorder MB
# (đã gắn ở [8]) nhưng đếm riêng cho từng loại qua reset.
MB.reset()
try:
    app.show_stage_detail(PID_D)
    dlg = find_toplevel("Giai đoạn ngâm")
    check("mở được dialog chi tiết", dlg is not None)
    root.update()
    btns = find_all(dlg, ttk.Button)
    names = [(b.cget("text") or "").strip() for b in btns]
    check("dialog có các nút ngày/ghim/ghi chú/mốc",
          "Hôm nay" in names and "Ghi mốc hiện tại" in names and "Ghim" in names
          and "Ghi chú…" in names and "Đóng" in names, str(names))
    labels = [l.cget("text") for l in find_all(dlg, tk.Label)]
    check("label 'Đồng hồ:' tồn tại", any(l == "Đồng hồ:" for l in labels))
    check("label 'Giai đoạn:' tồn tại", any(l == "Giai đoạn:" for l in labels))

    # GHÉP NHÃN→GIÁ TRỊ THEO HÀNG GRID của frame tóm tắt (specs L1891), KHÔNG dùng
    # "label kế tiếp" vì find_all là DFS không đảm bảo thứ tự tài liệu.
    # Nhãn đến từ specs = [Tài khoản, Giai đoạn, Đồng hồ, Bắt đầu / mail, Pha,
    # Bằng chứng, Cảnh báo]; giá trị là label col 1 cùng row.
    def _sumvals():
        for lab in find_all(dlg, tk.Label):
            if str(lab.cget("text")) == "Tài khoản:":
                return sum_values_of(lab.master)
        return {}

    sv = _sumvals()
    check("khối tóm tắt đọc được 7 dòng", len(sv) == 7, str(sorted(sv)))
    check("đồng hồ hiển thị A · 4 ngày · D13/4",
          "D13/4" in sv.get("Đồng hồ", "") and "4 ngày" in sv.get("Đồng hồ", ""),
          sv.get("Đồng hồ"))
    check("giai đoạn hiển thị S0", sv.get("Giai đoạn", "").startswith("S0"),
          sv.get("Giai đoạn"))
    check("một dòng chứa cả 2 mốc ngày (Bắt đầu / mail)",
          (_TODAY - dt.timedelta(days=12)).isoformat() in sv.get("Bắt đầu / mail", "")
          and "/" in sv.get("Bắt đầu / mail", ""), sv.get("Bắt đầu / mail"))
    check("nhãn pha dùng key 'Pha:' (không phải 'Chế độ ngâm:')",
          "Pha" in sv and "đang dùng" in sv.get("Pha", ""), sv.get("Pha"))
    # Đặt mail hôm nay -> đồng hồ chuyển B, stage S1
    hm_btns = [b for b in btns if (b.cget("text") or "").strip() == "Hôm nay"]
    check("có 2 nút 'Hôm nay' (start + mail)", len(hm_btns) >= 2, str(len(hm_btns)))
    hm_btns[1].invoke()
    root.update()
    sv = _sumvals()
    check("sau khi đặt mail: đồng hồ thành H1/7",
          "H1/7" in sv.get("Đồng hồ", "") and "7 ngày" in sv.get("Đồng hồ", ""),
          sv.get("Đồng hồ"))
    check("mail_date ghi xuống DB thật",
          db.get_profile_stage_rows()[PID_D]["mail_date"] == _TODAY.isoformat())
    check("stage đổi sang S1", sv.get("Giai đoạn", "").startswith("S1"),
          sv.get("Giai đoạn"))
    # Ghim pha
    pins = [b for b in btns if (b.cget("text") or "").strip() == "Ghim"]
    combos = find_all(dlg, ttk.Combobox)
    check("có combobox ghim pha", bool(combos))
    combos[0].set("3 · Cày YouTube")
    pins[0].invoke()
    root.update()
    check("phase_override=youtube vào DB",
          db.get_profile_stage_rows()[PID_D]["phase_override"] == "youtube")
    sv = _sumvals()
    # UI hiển thị nhãn ngắn ("3 · Cày YouTube") chứ không phải key "youtube"
    check("dòng 'Pha:' báo đang dùng youtube + ghim tay",
          "Cày YouTube" in sv.get("Pha", "") and "ghim tay" in sv.get("Pha", "")
          and "đề xuất: 2" in sv.get("Pha", ""),
          sv.get("Pha"))
    unpin = [b for b in btns if (b.cget("text") or "").strip() == "Bỏ ghim"]
    unpin[0].invoke()
    root.update()
    check("bỏ ghim -> phase_override rỗng",
          db.get_profile_stage_rows()[PID_D]["phase_override"] == "")
    # Ghi chú (askstring đã stub -> None -> không đổi)
    note_btns = [b for b in btns if (b.cget("text") or "").strip().startswith("Ghi chú")]
    note_btns[0].invoke()
    root.update()
    check("ghi chú None không làm hỏng dialog", find_toplevel("Giai đoạn ngâm") is not None)
    check("ghi chú None không ghi note",
          db.get_profile_stage_rows()[PID_D]["note"] == "")
    sd_real.askstring = lambda *a, **k: "acc test v150"
    note_btns[0].invoke()
    root.update()
    sd_real.askstring = askstring_real
    check("ghi chú lưu vào DB", db.get_profile_stage_rows()[PID_D]["note"] == "acc test v150")
    # Ghi mốc hiện tại -> stage_history. log_stage_change CHỐNG TRÙNG (bỏ qua khi
    # dòng cuối đã cùng stage) nên test seed trước 1 dòng stage khác để phép đếm
    # có ý nghĩa, rồi vẫn kiểm tra cả "dòng mới nhất là S1/manual".
    db.log_stage_change(PID_D, "S5", source="manual", note="seed de-dup-test")
    before = len(db.get_stage_history(PID_D))
    log_btns = [b for b in btns if (b.cget("text") or "").strip() == "Ghi mốc hiện tại"]
    log_btns[0].invoke()
    root.update()
    hist = db.get_stage_history(PID_D)
    check("ghi mốc tạo thêm đúng 1 dòng stage_history", len(hist) == before + 1,
          f"{before} -> {len(hist)}")
    check("dòng mới nhất là S1/manual",
          bool(hist) and hist[0]["stage"] == "S1" and hist[0]["source"] == "manual",
          str(hist[:1]))
    tree_hist = find_all(dlg, ttk.Treeview)
    check("dialog có Treeview lịch sử", bool(tree_hist))
    if tree_hist:
        hvals = [tree_hist[0].item(i, "values") for i in tree_hist[0].get_children()]
        check("lịch sử render dòng S1 manual",
              any(v and v[0] == "S1" and v[2] == "manual" for v in hvals), str(hvals))
    # Sau khi ghi, cache phải được DỰNG LẠI bằng dữ liệu mới (không phải để trống:
    # _stage_invalidate = cache=None + _stage_refresh(force=True) -> cache có lại).
    check("cache dựng lại sau khi ghi và mang dữ liệu mới",
          app._stage_cache is not None and PID_D in app._stage_cache
          and app._stage_cache[PID_D]["stage"] == "S1",
          str(app._stage_cache and app._stage_cache.get(PID_D, {}).get("stage")))
    click_btn(dlg, "Đóng")
    root.update()
    check("dialog đóng sạch", find_toplevel("Giai đoạn ngâm") is None)
    # pid rỗng -> không mở gì
    app.show_stage_detail("")
    root.update()
    check("pid rỗng không mở dialog", find_toplevel("Giai đoạn ngâm") is None)
    # acc chưa đặt ngày nào -> nút "Ghi mốc hiện tại" phải cảnh báo, không ghi DB
    MB.reset()
    app.show_stage_detail(PID_G3)
    dlg3 = find_toplevel("Giai đoạn ngâm")
    if dlg3 is not None:
        root.update()
        lb = [b for b in find_all(dlg3, ttk.Button)
              if (b.cget("text") or "").strip() == "Ghi mốc hiện tại"]
        lb[0].invoke()
        root.update()
        check("acc không giai đoạn -> cảnh báo khi ghi mốc",
              len(MB.titles("showwarning")) >= 1, str(MB.calls))
        check("acc không giai đoạn -> không ghi history",
              db.get_stage_history(PID_G3) == [])
        click_btn(dlg3, "Đóng")
        root.update()
    else:
        check("acc không giai đoạn -> mở được dialog", False, "find_toplevel fail")
finally:
    sd_real.askstring = askstring_real

# double-click / virtual event trên tab giai đoạn (phải lấy iid MỚI sau mọi lần
# _stage_refresh vì refresh xoá + chèn lại toàn bộ dòng)
app._stage_refresh(force=True)
root.update()
iid_g2 = {v["pid"]: iid for iid, v in app._stage_raw.items()}[PID_G2]
t.selection_set(iid_g2)
t.event_generate("<<ShowStageDetail>>")
root.update()
dlg2 = find_toplevel("Giai đoạn ngâm")
check("virtual event mở dialog đúng acc",
      dlg2 is not None and "Acc S4" in (dlg2.title() or ""),
      str(dlg2.title() if dlg2 else None))
if dlg2:
    click_btn(dlg2, "Đóng")
    root.update()
t.selection_remove(*t.get_children())
t.event_generate("<<ShowStageDetail>>")
root.update()
check("không chọn dòng -> không mở dialog", find_toplevel("Giai đoạn ngâm") is None)

# ---------------------------------------------------------------- 11. backfill qua UI
hr("[11] Backfill qua UI (run_stage_backfill)")
PID_UB = "PID-UIBACKFILL"
conn = sqlite3.connect(db.db_path)
conn.execute("INSERT INTO activity_history (profile_id, action, platform, url, title, created_at) "
             "VALUES (?,?,?,?,?,?)", (PID_UB, "read_news", "vnexpress.net", "https://vne.net",
                                      "bai", _ts(_TODAY - dt.timedelta(days=3))))
conn.execute("INSERT INTO alert_history (profile_id, query, created_at) VALUES (?,?,?)",
             (PID_UB, "nha dep", _ts(_TODAY - dt.timedelta(days=1))))
conn.commit()
conn.close()
# run_stage_backfill gọi messagebox qua TÊN ui_main.messagebox -> đã là recorder
# MB (gắn ở [8]). Điều khiển nó bằng MB.yes, KHÔNG patch module tkinter thật.
MB.yes = True
MB.reset()
try:
    app.run_stage_backfill()
    root.update()
    check("backfill hỏi xác nhận trước khi chạy",
          MB.titles("askyesno")[:1] == ["Tự điền từ dữ liệu cũ"], str(MB.calls))
    res_win = find_toplevel("Tự điền giai đoạn")
    check("mở dialog kết quả backfill", res_win is not None)
    # Nhãn tổng kết ở dialog này là ttk.Label (style Muted.TLabel), KHÔNG phải tk.Label
    txts = " | ".join(str(l.cget("text")) for l in
                      find_all(res_win, tk.Label) + find_all(res_win, ttk.Label)) if res_win else ""
    check("kết quả ghi số profile đã điền", "Đã điền ngày bắt đầu cho" in txts, txts[:200])
    rows_ub = db.get_profile_stage_rows()
    check("backfill điền start_date từ activity đầu tiên",
          PID_UB in rows_ub and rows_ub[PID_UB]["start_date"]
          == (_TODAY - dt.timedelta(days=3)).isoformat(),
          str(rows_ub.get(PID_UB)))
    check("mail_date VẪN trống trước khi bấm Dùng (chỉ gợi ý)",
          rows_ub.get(PID_UB, {}).get("mail_date", "") == "",
          str(rows_ub.get(PID_UB)))
    # Nút "Dùng" nằm trong rowf riêng của từng gợi ý -> chọn đúng row của PID_UB
    target_btn = None
    for rf in find_all(res_win, ttk.Frame):
        labs = [str(l.cget("text")) for l in rf.winfo_children()
                if isinstance(l, ttk.Label)]
        if any(PID_UB[:8] in x for x in labs):
            for b in rf.winfo_children():
                if isinstance(b, ttk.Button) and (b.cget("text") or "").strip() == "Dùng":
                    target_btn = b
                    break
        if target_btn is not None:
            break
    check("có nút 'Dùng' cho gợi ý mail của profile test", target_btn is not None)
    if target_btn is not None:
        target_btn.invoke()
        root.update()
        expect_hint = (_TODAY - dt.timedelta(days=1)).isoformat()
        check("bấm 'Dùng' -> mail_date = đúng ngày gợi ý (ngày alert đầu tiên)",
              db.get_profile_stage_rows()[PID_UB]["mail_date"] == expect_hint,
              str(db.get_profile_stage_rows()[PID_UB]))
        check("nút 'Dùng' đổi thành đã dùng",
              (target_btn.cget("text") or "").startswith("đã dùng"),
              target_btn.cget("text"))
        check("nút 'Dùng' bị disable sau khi dùng",
              target_btn.instate(["disabled"]), str(target_btn.state()))
    click_btn(res_win, "Đóng")
    root.update()
    check("đóng dialog kết quả", find_toplevel("Tự điền giai đoạn") is None)
    # từ chối ở hộp hỏi -> không chạy
    MB.yes = False
    MB.reset()
    app.run_stage_backfill()
    root.update()
    check("từ chối confirm -> không mở kết quả",
          find_toplevel("Tự điền giai đoạn") is None and MB.titles("askyesno")[:1]
          == ["Tự điền từ dữ liệu cũ"], str(MB.calls))
finally:
    MB.yes = True

# ---------------------------------------------------------------- 12. btn_stage + invalidate
hr("[12] Nút bảng giai đoạn + invalidate")
check("app có btn_stage", hasattr(app, "btn_stage"))
nb.select(0)
root.update()
app.btn_stage.invoke()
root.update()
check("btn_stage chọn tab giai đoạn", str(nb.tab(nb.select(), "text") or "").strip()
      == "GIAI ĐOẠN NGÂM", str(nb.tab(nb.select(), "text")))
app._stage_cache = {"x": {}}
app._stage_cache_at = time.time()
t_before = app._stage_cache_at
time.sleep(0.01)
app._stage_invalidate()
root.update()
# _stage_invalidate = cache=None rồi _stage_refresh(force=True) -> cache ĐƯỢC DỰNG
# LẠI bằng dữ liệu mới (không thể còn None). Kiểm tra: không còn key rác + stamp mới.
check("_stage_invalidate dựng lại cache sạch dữ liệu cũ",
      app._stage_cache is not None and "x" not in app._stage_cache
      and PID_G2 in app._stage_cache, str(list((app._stage_cache or {}).keys())[:5]))
check("_stage_invalidate cập nhật mốc cache", app._stage_cache_at > t_before,
      f"{t_before} -> {app._stage_cache_at}")
check("_stage_invalidate làm mới cả 2 bảng",
      callable(getattr(app, "_stage_refresh", None))
      and callable(getattr(app, "_board_refresh", None)))

# ---------------------------------------------------------------- 13. start_automation
hr("[13] start_automation: thứ tự tab + cảnh báo lệch pha")
# ping_api / run_thread_pool là METHOD của AutomationApp (gọi qua self.) -> patch trên
# class/instance, không phải tên module. run_thread_pool là thread nền thật -> stub im lặng,
# nếu không bot sẽ mở profile GPM giữa lúc test.
app.var_phase_label.set(ui.PHASE_LABEL_BY_KEY["clean"])
app.cbo_browser.set("GPM Login")
app.txt_api_port.delete(0, "end")
app.txt_api_port.insert(0, "9495")
app.spin_threads.delete(0, "end")
app.spin_threads.insert(0, "2")
app._rebuild_kw_rows(["ve gia re"], ["video nha"])
for r in app.profile_rows:
    if r.get("var") is None:
        # Dòng [10] chèn fixture không có BooleanVar (UI thật luôn có) -> cho vào
        # hàng KHÔNG tick để `start_automation` không ném AttributeError.
        r["var"] = tk.BooleanVar(value=False)
        r["hidden"] = False
        continue
    r["var"].set(True)
    r["hidden"] = False
# Acc S4/S5 (PID_G2) đề xuất pha khác "clean" -> phải có cảnh báo
sel = [r["id"] for r in app.profile_rows
       if r["var"].get() and not r["firefox"] and not r.get("hidden", False)]
check("4 hồ sơ test sẵn sàng chạy", sel == [PID_G1, PID_G2, PID_G3, PID_G4], str(sel))
# Ép cache giai đoạn dựng lại (max_age 5s có thể làm hộp lệch pha thấy dữ liệu cũ)
app._stage_cache = None
app._stage_cache_at = 0
ov_now = app._stage_overview_cached()
check("cache overview có PID_G2", PID_G2 in (ov_now or {}),
      str(sorted((ov_now or {}).keys())[:6]))
check("dữ liệu test có acc lệch pha với clean",
      any((ov_now.get(p, {}) or {}).get("effective_phase") not in (None, "clean")
          for p in sel), str({p: ov_now.get(p, {}).get("effective_phase") for p in sel}))
check("PID_G2 lệch pha (đề xuất youtube)",
      ov_now.get(PID_G2, {}).get("effective_phase") == "youtube",
      str(ov_now.get(PID_G2, {}).get("effective_phase")))
check("PID_G4 (ghim clean) KHÔNG bị coi là lệch",
      ov_now.get(PID_G4, {}).get("effective_phase") == "clean",
      str(ov_now.get(PID_G4, {}).get("effective_phase")))

MB.reset()
MB.yes = True
_rtp = ui.AutomationApp.run_thread_pool
app.ping_api = lambda *a, **k: True
ui.AutomationApp.run_thread_pool = lambda self, *a, **k: None
# v1.5.7: start_automation có thêm hộp xác nhận PHÂN BỔ CHỦ ĐỀ (Toplevel modal wait_window)
# -> stub trả True để test không treo chờ người bấm.
app.show_assignment_confirm = lambda *a, **k: True
try:
    app.start_automation()
    root.update()
    texts = [str(nb.tab(x, "text") or "").strip() for x in nb.tabs()]
    check("start: không nhân đôi tab giai đoạn",
          texts.count("GIAI ĐOẠN NGÂM") == 1, str(texts))
    # v1.5.7: thứ tự tab báo cáo = THỜI LƯỢNG CHẠY -> GIAI ĐOẠN NGÂM -> PHÂN BỔ CHỦ ĐỀ.
    check("start: tab phân bổ chủ đề CUỐI cùng", texts[-1] == "PHÂN BỔ CHỦ ĐỀ", str(texts))
    check("start: tab giai đoạn áp chót", texts[-2] == "GIAI ĐOẠN NGÂM", str(texts))
    check("start: board nằm trước tab giai đoạn",
          "THỜI LƯỢNG CHẠY" in texts and texts.index("THỜI LƯỢNG CHẠY") == len(texts) - 3,
          str(texts))
    check("start: slot nằm giữa MAIN và 3 tab báo cáo",
          texts[1].startswith("Slot") and len(texts) == 1 + 2 + 3, str(texts))
    titles = MB.titles("askyesno")
    check("start: hỏi cảnh báo lệch chế độ ngâm", titles[:1] == ["Lệch chế độ ngâm"], str(titles))
    q = " ".join(m for k, t, m in MB.calls if k == "askyesno")
    check("cảnh báo nêu acc + pha đề xuất", "đang ở giai đoạn KHÁC" in q and "đề xuất" in q,
          q[:250])
    check("cảnh báo nêu đúng 1/4 acc lệch", "1/4 acc" in q, q[:200])
    check("cảnh báo nêu PID 8 ký tự của acc lệch", PID_G2[:8] in q, q[:200])
    check("cảnh báo không tự đổi lựa chọn (chỉ hỏi)",
          app.var_phase_label.get() == ui.PHASE_LABEL_BY_KEY["clean"])
    check("start: không sinh hộp lỗi", MB.titles("showerror") == [], str(MB.calls))
    check("start: chuyển sang trạng thái đang chạy", app._running is True)
    check("start: số slot = min(threads 2, 4 hồ sơ) = 2", app._active_slots == [0, 1],
          str(app._active_slots))
    # Trả lời No -> phải dừng trước khi đổi UI
    app._running = False
    app._active_slots = []
    MB.reset()
    MB.yes = False
    for tab in list(nb.tabs())[1:]:
        nb.forget(tab)
    app.start_automation()
    root.update()
    check("No ở cảnh báo lệch pha -> KHÔNG chạy", app._running is False)
    check("No -> không tạo tab slot",
          [str(nb.tab(x, "text") or "").strip() for x in nb.tabs()] == ["MAIN"],
          str([nb.tab(x, "text") for x in nb.tabs()]))
    check("No -> vẫn hỏi đúng 1 lần cùng hộp thoại",
          MB.titles("askyesno") == ["Lệch chế độ ngâm"], str(MB.titles("askyesno")))
finally:
    MB.yes = True
    MB.reset()
    ui.AutomationApp.run_thread_pool = _rtp
    try:
        del app.ping_api          # trả về method thật của class
    except AttributeError:
        pass
    try:
        del app.show_assignment_confirm   # trả về method thật của class
    except AttributeError:
        pass
    app._running = False
    app._active_slots = []
    root.update()

# ---------------------------------------------------------------- 14. kiểm tra tĩnh
hr("[14] Kiểm tra tĩnh nguồn")
src_ui = open(os.path.join(HERE, "ui_main.py"), encoding="utf-8").read()
src_db = open(os.path.join(HERE, "database", "db_handler.py"), encoding="utf-8").read()
src_wu = open(os.path.join(HERE, "workflow", "warmup.py"), encoding="utf-8").read()


def _body(src, name):
    """Thân hàm `name` (từ `def name` tới `def` kế cùng cấp) — để assert phạm vi hẹp."""
    i = src.index(f"def {name}(")
    j = src.find("\n    def ", i + 1)
    return src[i:j if j != -1 else len(src)]

check("warmup.py KHÔNG bị đụng bởi giai đoạn ngâm",
      "compute_stage" not in src_wu and "stage_history" not in src_wu
      and "get_stage_overview" not in src_wu and "log_stage_change" not in src_wu)
check("start_automation tạo tab giai đoạn SAU tab board",
      src_ui.index("self._create_board_tab()", src_ui.index("def start_automation"))
      < src_ui.index("self._create_stage_tab()", src_ui.index("def start_automation")))
check("gọi _create_stage_tab ở cả __init__ lẫn start_automation",
      src_ui.count("self._create_stage_tab()") == 2, str(src_ui.count("self._create_stage_tab()")))
check("chỉ cảnh báo lệch pha, không tự đổi phase",
      "Vẫn chạy với chế độ đã chọn?" in src_ui
      and "self.var_phase_label.set" not in _body(src_ui, "start_automation")
      and "var_phase_label.set" not in _body(src_ui, "start_automation"))
check("worker tự ghi mốc giai đoạn source=auto",
      "db.log_stage_change(" in src_ui and 'source="auto"' in src_ui)
check("backfill UI không tự ghi mail", "mail_hints" in src_ui and "set_profile_mail_date" in src_ui)
check("db có migration stage (an toàn: backup trước ALTER)",
      "_migrate_stage_tracking" in src_db and "pre-migration-stage" in src_db)
check("compute_stage xử lý mail quá khứ (đồng hồ B thắng)",
      "mail_date" in src_db.split("def compute_stage")[1][:2500])
check("btn_stage nằm trong danh sách disable khi chạy",
      "btn_stage" in _body(src_ui, "start_automation")
      and "btn_stage" in _body(src_ui, "_set_utils_state"))
check("tab stage không đăng ký log_boxes (không nhận stdout)",
      "log_boxes[" not in _body(src_ui, "_create_stage_tab"))

# ---------------------------------------------------------------- 15. theme toggle
hr("[15] Đổi nền sáng/tối với tab giai đoạn đang mở")
# [13] dọn tab bằng nb.forget() nên phải dựng lại board + tab giai đoạn (đúng thứ tự gốc)
if [str(nb.tab(x, "text") or "").strip() for x in nb.tabs()][-1] != "GIAI ĐOẠN NGÂM":
    app._create_board_tab()
    app._create_stage_tab()
    root.update()
theme_before = app.theme_name
try:
    app._toggle_theme()
    root.update()
    check("toggle sang theme kia", app.theme_name != theme_before, app.theme_name)
    check("tab giai đoạn còn sau toggle",
          [str(nb.tab(x, "text") or "").strip() for x in nb.tabs()][-1] == "GIAI ĐOẠN NGÂM")
    app.show_stage_detail(PID_D)
    root.update()
    app._toggle_theme()
    root.update()
    check("toggle khi dialog chi tiết đang mở không crash", True)
    d = find_toplevel("Giai đoạn ngâm")
    if d:
        click_btn(d, "Đóng")
    root.update()
except Exception as e:
    check("theme toggle an toàn", False, repr(e))
finally:
    if app.theme_name != theme_before:
        try:
            app._toggle_theme()
            root.update()
        except Exception:
            pass

# ---------------------------------------------------------------- cleanup
hr("Cleanup")
try:
    root.destroy()
except Exception:
    pass
REAL_HASH_AFTER = _real_hash()
if REAL_HASH_BEFORE:
    check("DB thật của user không bị đụng", REAL_HASH_BEFORE == REAL_HASH_AFTER)

print(f"\nRESULT: PASS={PASS} FAIL={FAIL}")
print("SMOKE v1.5.0: ALL PASS" if FAIL == 0 else "SMOKE v1.5.0: COI CHUNG")
sys.exit(0 if FAIL == 0 else 1)
