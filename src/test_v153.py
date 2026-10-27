# -*- coding: utf-8 -*-
"""Smoke test v1.5.3 — 2 yêu cầu user 20/10/2026, kiểm tra OFFLINE (không cần browser):

  #1 HẠN MỨC PHÚT/NGÀY cho mỗi acc (khác "Mục tiêu vòng" = 1 chu trình):
     - db.get_today_seconds([pid]) = tổng duration_s các chu trình ĐÃ XONG HÔM NAY.
     - run_single_profile: hết hạn mức -> BỎ QUA acc (không mở browser, không sinh row chu trình).
     - còn ít thời gian -> SIẾT trần phiên (session_deadline_s) theo phần còn lại.
     - 0 = tắt hạn mức (hành vi y hệt v1.5.2).
  #2 GHIM CHỦ ĐỀ: ô nhập tay ở thẻ "CHỦ ĐỀ XUYÊN SUỐT" -> mọi profile dùng đúng chủ đề đó,
     bỏ qua random.choice(danh sách). Trống = bot tự chọn (hành vi cũ).

Chạy:  python src\\test_v153.py
DB test nằm ở thư mục tạm (GPM_BOT_DATA_DIR) — KHÔNG đụng data\\ thật.
"""
import os
import sys
import time
import tempfile
import datetime
import sqlite3

SRC = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SRC)
for p in (ROOT, SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

# Console test là pipe cp1252 -> print emoji của UI/warmup sẽ ném UnicodeEncodeError.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TMP = tempfile.mkdtemp(prefix="gpm_v153_")
os.environ["GPM_BOT_DATA_DIR"] = TMP

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


def hr(t):
    print("\n" + "=" * 70)
    print(t)
    print("=" * 70)


def read_src(name):
    with open(os.path.join(SRC, name), "r", encoding="utf-8") as f:
        return f.read()


NOW = datetime.datetime.now().isoformat(timespec="seconds")
YDAY = (datetime.datetime.now() - datetime.timedelta(days=1)).isoformat(timespec="seconds")

from src.database.db_handler import DatabaseHandler  # noqa: E402
from src import app_config                          # noqa: E402

DBP = os.path.join(TMP, "agent_logs.db")


# =====================================================================
hr("1. db.get_today_seconds — đếm giây ĐÃ NGÂM HÔM NAY theo profile")
# =====================================================================
db = DatabaseHandler(db_path=DBP)

check("DB trống -> {} (không lỗi)", db.get_today_seconds() == {}, str(db.get_today_seconds()))
check("DB trống + lọc pid -> {}", db.get_today_seconds(["PID-X"]) == {}, str(db.get_today_seconds(["PID-X"])))

db.log_cycle("PID-A", f"{YDAY}T09:00:00", f"{YDAY}T09:30:00", 1800.0, "ok", actions=5, phase="clean")
db.log_cycle("PID-A", f"{NOW[:10]}T08:00:00", f"{NOW[:10]}T08:10:00", 600.0, "ok", actions=4, phase="clean")
db.log_cycle("PID-A", f"{NOW[:10]}T09:00:00", f"{NOW[:10]}T09:05:00", 300.0, "error", actions=2, phase="clean")
db.log_cycle("PID-B", f"{NOW[:10]}T10:00:00", f"{NOW[:10]}T10:20:00", 1200.0, "stopped", actions=3, phase="mail")
db.log_cycle("PID-C", f"{YDAY}T11:00:00", f"{YDAY}T11:40:00", 2400.0, "ok", actions=6, phase="clean")

all_today = db.get_today_seconds()
check("Chỉ đếm row HÔM NAY (bỏ row hôm qua của PID-A)", all_today.get("PID-A") == 900.0, str(all_today.get("PID-A")))
check("PID-B = 1200s (status 'stopped' vẫn tính — thời gian đã ngâm là thật)", all_today.get("PID-B") == 1200.0,
      str(all_today.get("PID-B")))
check("PID-C không có row hôm nay -> không xuất hiện", "PID-C" not in all_today, str(sorted(all_today)))

only_a = db.get_today_seconds(["PID-A"])
check("Lọc pid: chỉ trả PID-A = 900", only_a == {"PID-A": 900.0}, str(only_a))
both = db.get_today_seconds(["PID-A", "PID-B", "PID-KHONG-CO"])
check("Lọc nhiều pid: trả đúng 2 pid có dữ liệu", both == {"PID-A": 900.0, "PID-B": 1200.0}, str(both))
check("Lọc pid rỗng -> {} (không chạy SQL 'IN ()')", db.get_today_seconds(["", None]) == {},
      str(db.get_today_seconds(["", None])))

# Không tạo row / không migration: chỉ SELECT
_tables = {r[0] for r in sqlite3.connect(DBP).execute("SELECT name FROM sqlite_master WHERE type='table'")}
check("get_today_seconds KHÔNG tạo bảng mới", "cycle_history" in _tables and "today_seconds" not in _tables,
      str(sorted(_tables))[:90])


# =====================================================================
hr("2. app_config — 2 key mới round-trip")
# =====================================================================
check("DEFAULTS có 'daily_minutes' = 30", app_config.DEFAULTS.get("daily_minutes") == 30,
      str(app_config.DEFAULTS.get("daily_minutes")))
check("DEFAULTS có 'pinned_theme' = ''", app_config.DEFAULTS.get("pinned_theme") == "",
      repr(app_config.DEFAULTS.get("pinned_theme")))
check("DEFAULTS: 2 key mới đúng KIỂU (int/str) — load_config lọc theo type",
      isinstance(app_config.DEFAULTS["daily_minutes"], int) and isinstance(app_config.DEFAULTS["pinned_theme"], str))

cfg0 = app_config.load_config()
check("load_config (chưa có file) -> daily_minutes 30", cfg0.get("daily_minutes") == 30, str(cfg0.get("daily_minutes")))
check("load_config (chưa có file) -> pinned_theme ''", cfg0.get("pinned_theme") == "", repr(cfg0.get("pinned_theme")))

cfg0["daily_minutes"] = 45
cfg0["pinned_theme"] = "chạy bộ buổi sáng"
check("save_config -> True", app_config.save_config(cfg0) is True)
cfg1 = app_config.load_config()
check("Round-trip daily_minutes 45", cfg1.get("daily_minutes") == 45, str(cfg1.get("daily_minutes")))
check("Round-trip pinned_theme (giữ dấu tiếng Việt)",
      cfg1.get("pinned_theme") == "chạy bộ buổi sáng", repr(cfg1.get("pinned_theme")))

cfg0["daily_minutes"] = 0
cfg0["pinned_theme"] = ""
app_config.save_config(cfg0)
cfg2 = app_config.load_config()
check("daily_minutes = 0 giữ nguyên (0 = TẮT hạn mức, không bị default ghi đè)",
      cfg2.get("daily_minutes") == 0, str(cfg2.get("daily_minutes")))
check("pinned_theme '' giữ nguyên", cfg2.get("pinned_theme") == "", repr(cfg2.get("pinned_theme")))


# =====================================================================
hr("3. GUI: spinbox Phút/ngày + ô Ghim chủ đề + helper")
# =====================================================================
import tkinter as tk  # noqa: E402
import src.ui_main as ui  # noqa: E402,F401

ui_root = tk.Tk()
app = ui.AutomationApp(ui_root)
ui_root.update()

check("Có spin_daily_min", hasattr(app, "spin_daily_min"))
check("Có ent_pinned_theme + var_pinned_theme",
      hasattr(app, "ent_pinned_theme") and hasattr(app, "var_pinned_theme"))
def _label_texts(widget):
    out = []
    try:
        for w in widget.winfo_children():
            if "Label" in w.winfo_class():
                try:
                    out.append(str(w.cget("text")))
                except Exception:
                    pass
            out.extend(_label_texts(w))
    except Exception:
        pass
    return out


_lbl_texts = _label_texts(app.spin_daily_min.master)
check("Nhãn spinbox ghi rõ 'phút/ngày'",
      any("phút/ngày" in t for t in _lbl_texts), _lbl_texts)


def set_spin(spin, val):
    spin.delete(0, "end")
    spin.insert(0, str(val))


set_spin(app.spin_daily_min, 0)
check("_daily_secs() = 0 khi spinbox 0 (TẮT)", app._daily_secs() == 0, str(app._daily_secs()))
set_spin(app.spin_daily_min, 45)
check("_daily_secs() = 2700 khi spinbox 45", app._daily_secs() == 2700, str(app._daily_secs()))
set_spin(app.spin_daily_min, 1)
check("_daily_secs() = 60 khi spinbox 1", app._daily_secs() == 60, str(app._daily_secs()))
set_spin(app.spin_daily_min, "abc")
check("_daily_secs() = 1800 (mặc định 30 phút) khi nhập rác — KHÔNG tắt hạn mức oan",
      app._daily_secs() == 1800, str(app._daily_secs()))
set_spin(app.spin_daily_min, 30)

app.var_pinned_theme.set("   chạy bộ   ")
check("_pinned_theme_text() strip khoảng trắng", app._pinned_theme_text() == "chạy bộ",
      repr(app._pinned_theme_text()))
app.var_pinned_theme.set("")
check("_pinned_theme_text() = '' khi để trống (bot tự chọn)", app._pinned_theme_text() == "",
      repr(app._pinned_theme_text()))

app.var_pinned_theme.set("chạy bộ")
app.save_current_config()
_c = app_config.load_config()
check("save_current_config lưu pinned_theme", _c.get("pinned_theme") == "chạy bộ", repr(_c.get("pinned_theme")))
check("save_current_config lưu daily_minutes = 30", _c.get("daily_minutes") == 30, str(_c.get("daily_minutes")))
app.var_pinned_theme.set("")
app.save_current_config()


# =====================================================================
hr("4. run_single_profile — cổng HẠN MỨC NGÀY + GHIM CHỦ ĐỀ (không mở browser)")
# =====================================================================
class FakeWorkflow:
    made = []

    def __init__(self, *a, **k):
        self.kw = k
        self.session_deadline_s = 0
        FakeWorkflow.made.append(self)

    def run_random_session(self, total_actions=0):
        raise RuntimeError("STUB-RUN-RANDOM")


class FakeController:
    def __init__(self, ws_url):
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


real_wf, real_bc = ui.WarmupWorkflow, ui.BrowserController
real_adj, real_sleep = ui.adjust_window_bounds, time.sleep
ui.WarmupWorkflow = FakeWorkflow
ui.BrowserController = FakeController
ui.adjust_window_bounds = lambda *a, **k: None
ui.time.sleep = lambda *a, **k: None
ui.STOP_EVENT.clear()

THEMES = [{"google_query": "du lich", "youtube_query": "travel"},
          {"google_query": "chay bo", "youtube_query": "running"}]


def run_case(pid, **kw):
    """Chạy 1 nhánh run_single_profile; trả (số Workflow được tạo, list instance)."""
    before = len(FakeWorkflow.made)
    ui.SLOT_CYCLE_INFO.pop("Slot 1", None)
    try:
        ui.run_single_profile(FakeAPI(), pid, f"Profile {pid}", THEMES,
                              slot_index=0, screen_w=1200, screen_h=800,
                              skip_youtube=False, skip_random_keywords=False, **kw)
    except Exception:
        pass
    return len(FakeWorkflow.made) - before, FakeWorkflow.made[before:]


try:
    # 4a. daily_seconds = 0 -> tắt hạn mức, hành vi y hệt v1.5.2
    n, made = run_case("PID-DAY-OFF", daily_seconds=0, pinned_theme="")
    check("TẮT hạn mức: vẫn chạy bình thường (Workflow được tạo)", n == 1, f"n={n}")
    check("TẮT hạn mức: session_deadline_s = 0 (để core random 15-30 phút)",
          made and made[0].session_deadline_s == 0, str(made and made[0].session_deadline_s))

    # 4b. Ghim chủ đề -> đúng chủ đề đó, bỏ qua danh sách
    n, made = run_case("PID-PIN", daily_seconds=0, pinned_theme="chạy bộ 5km mỗi sáng")
    th = (made[0].kw.get("session_theme") or {}) if made else {}
    check("GHIM chủ đề: google_query = chủ đề ghim", th.get("google_query") == "chạy bộ 5km mỗi sáng",
          repr(th.get("google_query")))
    check("GHIM chủ đề: youtube_query = cùng chủ đề ghim", th.get("youtube_query") == "chạy bộ 5km mỗi sáng",
          repr(th.get("youtube_query")))

    # 4c. Không ghim -> chủ đề lấy từ danh sách (không bịa)
    n, made = run_case("PID-NOPIN", daily_seconds=0, pinned_theme="")
    th = (made[0].kw.get("session_theme") or {}) if made else {}
    check("KHÔNG ghim: chủ đề vẫn thuộc danh sách themes",
          th in THEMES, repr(th.get("google_query")))

    # 4d. Còn 10 phút hôm nay -> siết trần phiên = 600s
    n, made = run_case("PID-DAY-SHORT", daily_seconds=600, pinned_theme="")
    check("Còn 600s: chạy (600 > 120)", n == 1, f"n={n}")
    check("Còn 600s: session_deadline_s bị siết = 600",
          made and made[0].session_deadline_s == 600, str(made and made[0].session_deadline_s))

    # 4e. Còn 50 phút -> trần random core (tối đa 1800s) đã an toàn -> để 0
    n, made = run_case("PID-DAY-LONG", daily_seconds=3000, pinned_theme="")
    check("Còn 3000s: KHÔNG siết (để core random 15-30 phút)", made and made[0].session_deadline_s == 0,
          str(made and made[0].session_deadline_s))

    # 4f. Mục tiêu vòng cố định 1200s nhưng hôm nay chỉ còn 600s -> siết về 600
    n, made = run_case("PID-DAY-BOTH", fixed_target_s=1200, daily_seconds=600, pinned_theme="")
    check("Mục tiêu vòng 1200 + còn 600 -> trần phiên = 600 (lấy min)",
          made and made[0].session_deadline_s == 600, str(made and made[0].session_deadline_s))

    # 4g. Mục tiêu vòng 300 < phần còn lại 600 -> GIỮ 300 (không nới trần)
    n, made = run_case("PID-DAY-BOTH2", fixed_target_s=300, daily_seconds=600, pinned_theme="")
    check("Mục tiêu vòng 300 + còn 600 -> giữ 300 (không nới)",
          made and made[0].session_deadline_s == 300, str(made and made[0].session_deadline_s))

    # 4h. ĐÃ NGÂM ĐỦ hôm nay -> BỎ QUA: không mở browser, không sinh row chu trình
    db.log_cycle("PID-DAY-FULL", f"{NOW[:10]}T07:00:00", f"{NOW[:10]}T07:10:00", 600.0,
                 "ok", actions=4, phase="clean")
    n, made = run_case("PID-DAY-FULL", daily_seconds=600, pinned_theme="")
    check("Hết hạn mức: KHÔNG tạo Workflow (không mở trình duyệt)", n == 0, f"n={n}")
    check("Hết hạn mức: KHÔNG sinh row chu trình rỗng", ui.SLOT_CYCLE_INFO.get("Slot 1") is None,
          str(ui.SLOT_CYCLE_INFO.get("Slot 1")))

    # 4i. Đã ngâm 500/600 -> còn 100s (< ngưỡng 120) -> cũng bỏ qua (không mở browser 1 phút)
    db.log_cycle("PID-DAY-NEAR", f"{NOW[:10]}T07:00:00", f"{NOW[:10]}T07:08:20", 500.0,
                 "ok", actions=3, phase="clean")
    n, made = run_case("PID-DAY-NEAR", daily_seconds=600, pinned_theme="")
    check("Còn < 120s: bỏ qua (tránh mở browser cho phiên < 2 phút)", n == 0, f"n={n}")

    # 4j. Đã ngâm 300/600 -> còn 300s > 120 -> vẫn chạy, trần = 300
    db.log_cycle("PID-DAY-HALF", f"{NOW[:10]}T07:00:00", f"{NOW[:10]}T07:05:00", 300.0,
                 "ok", actions=3, phase="clean")
    n, made = run_case("PID-DAY-HALF", daily_seconds=600, pinned_theme="")
    check("Còn 300s: vẫn chạy", n == 1, f"n={n}")
    check("Còn 300s: trần phiên = 300 (phần còn lại của ngày)",
          made and made[0].session_deadline_s == 300, str(made and made[0].session_deadline_s))
finally:
    ui.WarmupWorkflow, ui.BrowserController = real_wf, real_bc
    ui.adjust_window_bounds, ui.time.sleep = real_adj, real_sleep

# 4k. DB thật có row hôm nay -> lần chạy sau bị trừ tiếp (không reset trong ngày)
check("DB đã ghi nhận thời gian hôm nay của các acc test (cộng dồn trong ngày)",
      db.get_today_seconds(["PID-DAY-FULL"]).get("PID-DAY-FULL") == 600.0,
      str(db.get_today_seconds(["PID-DAY-FULL"])))


# =====================================================================
hr("5. Assertion TĨNH trên source (chống tái phát / hồi quy)")
# =====================================================================
ui_src = read_src("ui_main.py")
cfg_src = read_src("app_config.py")
db_src = read_src(os.path.join("database", "db_handler.py"))
v152_src = read_src("test_v152.py")

check("ui: có spin_daily_min", "spin_daily_min" in ui_src)
check("ui: có ent_pinned_theme", "ent_pinned_theme" in ui_src)
check("ui: có _daily_secs", "def _daily_secs(self)" in ui_src)
check("ui: có _pinned_theme_text", "def _pinned_theme_text(self)" in ui_src)
check("ui: log 'Hạn mức ngày' trước khi chạy", "Hạn mức ngày" in ui_src)
check("ui: log 'hết hạn mức ngày' khi bỏ qua", "hết hạn mức ngày" in ui_src)
check("ui: log 'Chủ đề GHIM'", "Chủ đề GHIM" in ui_src)
check("ui: log 'Trần phiên siết theo hạn mức ngày'", "Trần phiên siết theo hạn mức ngày" in ui_src)
check("ui: ngưỡng bỏ qua là 120 giây", "daily_left <= 120" in ui_src)

# Trần phiên v1.5.2 phải giữ NGUYÊN VĂN (test_v152 assert dòng này)
V152_DEADLINE = "warmup.session_deadline_s = int(fixed_target_s) if fixed_target_s and fixed_target_s > 0 else 0"
check("ui: giữ nguyên dòng trần phiên v1.5.2 (byte-identical)", V152_DEADLINE in ui_src)
check("test_v152 vẫn assert đúng dòng đó", V152_DEADLINE in v152_src or "warmup.session_deadline_s = int(fixed_target_s)" in v152_src)
check("ui: total_actions vẫn random 4..8 (test_v152 assert)", "total_actions = random.randint(4, 8)" in ui_src)

# Luồng tham số 15 vị trí: Thread -> run_thread_pool -> executor.submit -> worker_wrapper -> run_single_profile
check("ui: Thread args kết thúc bằng '...pinned_theme, kw_lang' (v1.6.1 +ngôn ngữ)",
      "fixed_target_s, daily_seconds, pinned_theme, kw_lang), daemon=True)" in ui_src)
check("ui: executor.submit truyền đủ tham số cuối (+keyword_lang v1.6.1)",
      "fixed_target_s, daily_seconds, pinned_theme, keyword_lang) for pid in profiles]" in ui_src)
check("ui: run_single_profile nhận 2 param mới có default 0/''",
      'daily_seconds=0, pinned_theme=""' in ui_src)
check("ui: worker_wrapper nhận 2 param mới có default 0/''",
      ui_src.count('daily_seconds=0, pinned_theme=""') >= 3,
      str(ui_src.count('daily_seconds=0, pinned_theme=""')))
check("ui: run_thread_pool nhận param mới (+keyword_lang v1.6.1)", "def run_thread_pool(" in ui_src and
      "daily_seconds=0, pinned_theme=\"\", keyword_lang=\"en\"):" in ui_src)

check("app_config: DEFAULTS có daily_minutes", '"daily_minutes": 30' in cfg_src)
check("app_config: DEFAULTS có pinned_theme", '"pinned_theme": ""' in cfg_src)
check("db: có get_today_seconds", "def get_today_seconds(self" in db_src)
check("db: get_today_seconds dùng date(finished_at) = hôm nay",
      "date(finished_at) = date('now','localtime')" in db_src)
check("db: get_today_seconds không ALTER TABLE",
      "ALTER TABLE" not in db_src.split("def get_today_seconds")[1].split("def ")[0])


# =====================================================================
hr("KET QUA")
# =====================================================================
try:
    ui_root.destroy()
except Exception:
    pass
try:
    import shutil
    shutil.rmtree(TMP, ignore_errors=True)
except Exception:
    pass

print(f"PASS: {PASS}   FAIL: {FAIL}")
print("SMOKE v1.5.3: ALL PASS" if FAIL == 0 else f"SMOKE v1.5.3: {FAIL} FAIL")
sys.exit(0 if FAIL == 0 else 1)
