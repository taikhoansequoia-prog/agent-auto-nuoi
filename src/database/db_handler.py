import sqlite3
import datetime
import os
import shutil
import sys

def _say(msg):
    """In ra console một cách CHỐNG TREO/CHỐNG SẬP.

    Bối cảnh (v1.5.0): EXE PyInstaller chạy với stdout pipe mã hoá **cp1252**, nên mọi
    ``print`` chứa tiếng Việt có dấu raise UnicodeEncodeError. Tầng DB được gọi NGAY LÚC
    mở app (di chuyển schema, backup) -- TRƯỚC khi ``ui_main`` kịp thay sys.stdout bằng
    ThreadSafeStdout -- nên một dấu ``Đ`` trong log backup từng làm sập cả ứng dụng.
    Vì vậy mọi log của tầng DB đi qua đây: thử in nguyên văn, nếu encoding không nhận
    thì thay ký tự lỗi bằng '?' (mất dấu nhưng giữ được dòng log và giữ được app).
    """
    try:
        print(msg)
        return
    except UnicodeEncodeError:
        pass
    except Exception:
        return
    try:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(str(msg).encode(enc, "replace").decode(enc, "replace"))
    except Exception:
        pass



# ================= GIAI ĐOẠN NGÂM (v1.5.0) — mô hình 6 giai đoạn theo sheet SOP =================
# Sheet "Auto ngâm mail" định nghĩa 2 đồng hồ khác nhau:
#   Đồng hồ A (từ start_date): Giai đoạn 0 = Ngày 1..4, lắp proxy CHƯA có mail.
#   Đồng hồ B (từ mail_date):  Ngày 1 = lần login Gmail đầu tiên -> mốc Hagrid 7 ngày.
# Bảng dưới quy đổi 2 đồng hồ đó thành 6 mã S0..S5 để UI/DB nói cùng 1 ngôn ngữ.
STAGE_CODES = ["S0", "S1", "S2", "S3", "S4", "S5"]
STAGE_NAMES = {
    "S0": "Làm ấm profile (proxy, chưa mail)",
    "S1": "Móng bảo mật",
    "S2": "Mô phỏng hành vi",
    "S3": "Định hình thuật toán",
    "S4": "Ngâm kênh",
    "S5": "Vượt Hagrid",
}
# Nhãn "Giai đoạn N" đúng như sheet (S1 = Giai đoạn 1 ... S5 = Giai đoạn 4) để user đối chiếu.
STAGE_SHEET_LABELS = {
    "S0": "Giai đoạn 0",
    "S1": "Giai đoạn 1",
    "S2": "Giai đoạn 2",
    "S3": "Giai đoạn 3",
    "S4": "Ngâm kênh",
    "S5": "Giai đoạn 4",
}
STAGE0_DAYS = 4              # S0 = Ngày 1..4 tính từ start_date
HAGRID_DAYS = 7              # đồng hồ B: 7 ngày để mở khoá hành động nhạy cảm
# Pha bot (workflow/warmup.py) suy ra từ giai đoạn — người vận hành có thể ép bằng phase_override.
STAGE_SUGGESTED_PHASE = {"S0": "clean", "S1": "mail", "S2": "mail",
                         "S3": "mail", "S4": "youtube", "S5": "youtube"}
VALID_PHASES = ("clean", "mail", "youtube")


def _parse_iso_date(value):
    """'YYYY-MM-DD' -> datetime.date. Rỗng/sai -> None."""
    try:
        return datetime.date.fromisoformat(str(value).strip())
    except Exception:
        return None


def compute_stage(start_date, mail_date, today=None):
    """
    Tính giai đoạn hiện tại của 1 profile từ 2 mốc ngày (logic THUẦN, không đọc DB).

    start_date: ngày bắt đầu ngâm proxy ('YYYY-MM-DD') — mở đồng hồ A (S0).
    mail_date : ngày login Gmail đầu tiên ('YYYY-MM-DD') — mở đồng hồ B (S1..S5).
    today     : datetime.date | None (mặc định hôm nay) — cho phép test bơm ngày.

    Trả về dict:
        stage        'S0'..'S5' | '' (chưa có mốc ngày nào)
        stage_name   tên tiếng Việt
        sheet_label  'Giai đoạn 0'..'Giai đoạn 4' | 'Ngâm kênh'
        clock        'A' (S0) | 'B' (S1+) | ''
        day_no       số ngày thứ N trong đồng hồ đang chạy (1-based)
        day_total    tổng số ngày của đồng hồ (4 cho A, 7 cho B)
        day_label    'D2/4' | 'H5/7'
        days_left    số ngày còn lại tới mốc kế (>=0)
        overdue      True khi đã quá mốc mà chưa sang giai đoạn kế
        offset       số ngày kể từ mốc neo (âm = mốc ở tương lai)
    """
    today = today or datetime.date.today()
    out = {"stage": "", "stage_name": "", "sheet_label": "", "clock": "",
           "day_no": None, "day_total": None, "day_label": "", "days_left": None,
           "overdue": False, "offset": None, "start_date": start_date or "",
           "mail_date": mail_date or ""}

    md = _parse_iso_date(mail_date)
    if md is not None:
        offset = (today - md).days
        out["offset"] = offset
        if offset <= 0:
            stage = "S1"
        elif offset <= 3:
            stage = "S2"
        elif offset == 4:
            stage = "S3"
        elif offset == 5:
            stage = "S4"
        else:
            stage = "S5"
        day_no = offset + 1
        if day_no < 1:
            day_no = 1
        out.update(stage=stage, clock="B", day_no=day_no, day_total=HAGRID_DAYS,
                   day_label=f"H{day_no}/{HAGRID_DAYS}",
                   days_left=max(0, HAGRID_DAYS - day_no))
        if offset < 0:
            out["overdue"] = True   # mail_date ở tương lai — dữ liệu nhập sai
    else:
        sd = _parse_iso_date(start_date)
        if sd is not None:
            offset = (today - sd).days
            day_no = offset + 1
            out["offset"] = offset
            if day_no >= 1:
                stage = "S0"        # kể cả đã quá 4 ngày vẫn là S0 nhưng đánh dấu overdue
                out.update(stage=stage, clock="A", day_no=day_no, day_total=STAGE0_DAYS,
                           day_label=f"D{day_no}/{STAGE0_DAYS}",
                           days_left=max(0, STAGE0_DAYS - day_no + 1),
                           overdue=day_no > STAGE0_DAYS)

    if out["stage"]:
        out["stage_name"] = STAGE_NAMES[out["stage"]]
        out["sheet_label"] = STAGE_SHEET_LABELS[out["stage"]]
    return out


def suggested_phase(stage):
    """Pha bot nên dùng cho giai đoạn này ('clean'/'mail'/'youtube'); stage rỗng -> 'clean'."""
    return STAGE_SUGGESTED_PHASE.get(stage or "", "clean")


class DatabaseHandler:
    def __init__(self, db_path=None):
        """
        Khởi tạo kết nối tới database SQLite.
        Nếu thư mục 'data' chưa có, sẽ tự động tạo.

        v1.3.0: mặc định dùng src.paths.db_path() (repo-root data/, frozen-aware,
        KHÔNG phụ thuộc cwd). Call site cũ truyền db_path vẫn hoạt động.
        """
        if db_path is None:
            try:
                from src.paths import db_path as _default_db_path
                db_path = _default_db_path()
            except Exception:
                db_path = "data/agent_logs.db"
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self.db_path = db_path
        self._create_tables()

    def _create_tables(self):
        """
        Tạo bảng 'subscriptions' để lưu lịch sử nhấn nút.
        Chỉ lưu ID Profile và mốc thời gian thực hiện Sub gần nhất.
        Tạo bảng 'alert_history' để lưu lịch sử tạo Google Alert theo profile.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                profile_id TEXT PRIMARY KEY,
                last_sub_date TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alert_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id TEXT,
                query TEXT,
                created_at TEXT
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_alert_history_profile
            ON alert_history (profile_id, created_at)
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS activity_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id TEXT,
                action TEXT,
                platform TEXT,
                url TEXT,
                title TEXT,
                created_at TEXT
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_activity_history_profile
            ON activity_history (profile_id, created_at)
        ''')
        # v1.3.5: mốc nuôi acc 7 ngày — 'profile_timeline' lưu NGÀY BẮT ĐẦU do người vận hành tự đặt
        # (Ngày 1 = Giai đoạn 0: lắp proxy, chưa lắp mail), 'milestone_history' = lịch sử popup thông báo
        # mốc (dedup: mỗi mốc chỉ thông báo 1 lần/profile). Bảng MỚI hoàn toàn — CREATE IF NOT EXISTS,
        # không ALTER nên không cần backup migration.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS profile_timeline (
                profile_id TEXT PRIMARY KEY,
                start_date TEXT,
                updated_at TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS milestone_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id TEXT,
                milestone TEXT,
                notified_at TEXT
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_milestone_history_profile
            ON milestone_history (profile_id, milestone)
        ''')
        # v1.4.0: THỜI GIAN NGÂM THEO CHU TRÌNH — 1 dòng = 1 lần chạy 1 profile ở UI
        # (worker ghi, KHÔNG đụng warmup.py). status: 'ok' | 'error' | 'stopped'
        # (chu trình lỗi/dừng giữa chừng VẪN ghi — số liệu trung thực). Bảng mới hoàn toàn,
        # CREATE IF NOT EXISTS, không ALTER nên không cần backup migration.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cycle_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id TEXT,
                started_at TEXT,
                finished_at TEXT,
                duration_s REAL,
                status TEXT,
                actions INTEGER,
                phase TEXT,
                error TEXT,
                target_s REAL
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cycle_history_profile
            ON cycle_history (profile_id, finished_at)
        ''')
        # v1.5.0: GIAI ĐOẠN NGÂM (S0..S5) — 'stage_history' = sổ append-only ghi MỌI lần đổi
        # giai đoạn của 1 profile (source: auto|manual|backfill) để truy vết & hiển thị lịch sử.
        # Bảng mới hoàn toàn: CREATE IF NOT EXISTS, không ALTER -> không cần backup migration.
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stage_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                entered_at TEXT NOT NULL,
                source TEXT NOT NULL,
                note TEXT
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_stage_history_profile
            ON stage_history (profile_id, entered_at)
        ''')
        conn.commit()
        conn.close()
        # Sprint 2: bảo đảm schema mới (status/duration_s/error) — idempotent, tự backup trước khi đổi
        self._migrate_activity_history()
        # v1.4.1: thêm cột target_s cho DB đã tạo từ v1.4.0 — idempotent, backup trước khi đổi
        self._migrate_cycle_history()
        # v1.5.0: thêm 4 cột giai đoạn cho profile_timeline — idempotent, backup trước khi đổi
        self._migrate_stage_tracking()

    def backup_database(self, reason="manual"):
        """
        Sprint 2: copy DB hiện tại sang data/backup/ kèm timestamp trong tên file.
        Best-effort: lỗi chỉ in cảnh báo, trả về None. Thành công trả về đường dẫn backup.
        """
        try:
            if not os.path.exists(self.db_path):
                return None
            backup_dir = os.path.join(os.path.dirname(self.db_path) or ".", "backup")
            os.makedirs(backup_dir, exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            dst = os.path.join(backup_dir, f"agent_logs_{stamp}.db")
            shutil.copy2(self.db_path, dst)
            _say(f"[+] Đã backup DB ({reason}) -> {dst}")
            return dst
        except Exception as e:
            _say(f"[!] Backup DB lỗi (bỏ qua, không ảnh hưởng bot): {e}")
            return None

    def _migrate_activity_history(self):
        """
        Sprint 2: thêm cột status TEXT / duration_s REAL / error TEXT vào activity_history.
        Idempotent (PRAGMA kiểm tra trước, chỉ ALTER khi thiếu). Nếu thực sự đổi schema,
        BẮT BUỘC backup trước (bài học CTO: DB chứa lịch sử nuôi acc, mất là đui).
        Mọi lỗi chỉ in cảnh báo — không được chặn khởi động app.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(activity_history)")
            cols = {r[1] for r in cursor.fetchall()}
            wanted = [("status", "TEXT"), ("duration_s", "REAL"), ("error", "TEXT")]
            missing = [(n, t) for n, t in wanted if n not in cols]
            if not missing:
                conn.close()
                return
            backup_path = self.backup_database(reason="pre-migration")
            if not backup_path:
                _say("[!] Không backup được trước migration — BỎ QUA migration an toàn.")
                conn.close()
                return
            for name, typ in missing:
                cursor.execute(f"ALTER TABLE activity_history ADD COLUMN {name} {typ}")
            conn.commit()
            conn.close()
            _say(f"[+] Migration activity_history xong: thêm {', '.join(n for n, _ in missing)}")
        except Exception as e:
            _say(f"[!] Migration activity_history lỗi (bỏ qua): {e}")

    def _migrate_cycle_history(self):
        """
        v1.4.1: thêm cột target_s REAL vào cycle_history (mục tiêu ngẫu nhiên của từng vòng —
        mỗi profile/vòng một số khác nhau). Idempotent (PRAGMA kiểm tra trước, chỉ ALTER khi thiếu).
        DB tạo từ v1.4.0 thiếu cột này -> backup trước khi ALTER. Lỗi chỉ in cảnh báo.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(cycle_history)")
            cols = {r[1] for r in cursor.fetchall()}
            if "target_s" in cols:
                conn.close()
                return
            backup_path = self.backup_database(reason="pre-migration-cycle-target")
            if not backup_path:
                _say("[!] Không backup được trước migration cycle_history — BỎ QUA migration an toàn.")
                conn.close()
                return
            cursor.execute("ALTER TABLE cycle_history ADD COLUMN target_s REAL")
            conn.commit()
            conn.close()
            _say("[+] Migration cycle_history xong: thêm target_s")
        except Exception as e:
            _say(f"[!] Migration cycle_history lỗi (bỏ qua): {e}")

    def _migrate_stage_tracking(self):
        """
        v1.5.0: bổ sung 4 cột cho 'profile_timeline' (DB tạo từ v1.3.5 chưa có):
            mail_date      'YYYY-MM-DD' — ngày login Gmail ĐẦU TIÊN (mốc khởi động đồng hồ Hagrid 7 ngày)
            phase_override '' | clean | mail | youtube — người vận hành ép pha, ưu tiên hơn pha suy ra
            niche          chủ đề ngách của kênh (dùng từ giai đoạn S4)
            note           ghi chú tự do
        Idempotent (PRAGMA table_info). BẮT BUỘC backup trước khi ALTER; backup fail -> bỏ qua an toàn.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(profile_timeline)")
            cols = {r[1] for r in cursor.fetchall()}
            wanted = [("mail_date", "TEXT"), ("phase_override", "TEXT"),
                      ("niche", "TEXT"), ("note", "TEXT")]
            missing = [(n, t) for n, t in wanted if n not in cols]
            if not missing:
                conn.close()
                return
            backup_path = self.backup_database(reason="pre-migration-stage")
            if not backup_path:
                _say("[!] Không backup được trước migration stage — BỎ QUA migration an toàn.")
                conn.close()
                return
            for name, typ in missing:
                cursor.execute(f"ALTER TABLE profile_timeline ADD COLUMN {name} {typ}")
            conn.commit()
            conn.close()
            _say("[+] Migration stage xong: thêm " + ", ".join(n for n, _ in missing))
        except Exception as e:
            _say(f"[!] Migration stage lỗi (bỏ qua): {e}")

    def can_subscribe_today(self, profile_id):
        """
        Kiểm tra xem hôm nay profile này đã nhấn Sub chưa.
        Trả về True (được phép Sub) hoặc False (chỉ được xem, không được Sub).
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Lấy ngày hiện tại theo chuẩn YYYY-MM-DD
        today_str = datetime.date.today().isoformat()
        
        cursor.execute("SELECT last_sub_date FROM subscriptions WHERE profile_id=?", (profile_id,))
        row = cursor.fetchone()
        conn.close()
        
        # Nếu đã có dữ liệu và ngày cuối cùng sub chính là hôm nay
        if row and row[0] == today_str:
            _say(f"[*] Profile {profile_id} đã hết lượt Sub hôm nay. Sẽ chuyển sang chế độ chỉ Đọc báo/Xem video.")
            return False
                
        _say(f"[+] Profile {profile_id} chưa Sub hôm nay. Đủ điều kiện thực hiện kịch bản Đăng ký kênh.")
        return True

    def log_sub_success(self, profile_id):
        """
        Ghi nhận profile đã thực hiện thành công việc Sub vào database.
        Hàm này chỉ được gọi KHI VÀ CHỈ KHI Playwright + AI đã click thành công.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        today_str = datetime.date.today().isoformat()
        
        # Lệnh REPLACE sẽ tự động Update nếu ID đã tồn tại, hoặc Insert nếu là ID mới
        cursor.execute('''
            REPLACE INTO subscriptions (profile_id, last_sub_date) 
            VALUES (?, ?)
        ''', (profile_id, today_str))
        
        conn.commit()
        conn.close()
        _say(f"[+] Đã ghi log Database: Profile {profile_id} vừa Sub thành công vào lúc {today_str}.")

    # ================= GOOGLE ALERTS =================
    def alert_exists(self, profile_id, query):
        """
        Kiểm tra profile này đã từng tạo alert cho đúng query chưa (không phân biệt hoa/thường).
        Trả về True nếu đã có -> không tạo trùng.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM alert_history WHERE profile_id=? AND LOWER(query)=LOWER(?) LIMIT 1",
            (profile_id, query.strip().lower()),
        )
        found = cursor.fetchone() is not None
        conn.close()
        return found

    def can_create_alert_week(self, profile_id, days=7):
        """
        Giới hạn nhịp sinh học: mỗi profile chỉ tạo tối đa 1 alert mới trong `days` ngày gần nhất.
        Trả về True nếu được phép tạo, False nếu trong cửa sổ đã tạo rồi.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        since = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat(timespec="seconds")
        cursor.execute(
            "SELECT COUNT(*) FROM alert_history WHERE profile_id=? AND created_at>=?",
            (profile_id, since),
        )
        count = cursor.fetchone()[0]
        conn.close()
        if count > 0:
            _say(f"[*] Profile {profile_id} đã tạo alert trong {days} ngày gần nhất. Bỏ qua tạo mới.")
            return False
        return True

    def log_alert_created(self, profile_id, query):
        """
        Ghi nhận profile vừa tạo thành công một Google Alert cho `query`.
        Chỉ gọi khi Playwright xác nhận alert đã xuất hiện trong danh sách.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now_str = datetime.datetime.now().isoformat(timespec="seconds")
        cursor.execute(
            "INSERT INTO alert_history (profile_id, query, created_at) VALUES (?, ?, ?)",
            (profile_id, query.strip(), now_str),
        )
        conn.commit()
        conn.close()
        _say(f"[+] Đã ghi log Database: Profile {profile_id} vừa tạo alert '{query.strip()}' lúc {now_str}.")

    # ================= ACTIVITY / REPORTING (Task 5) =================
    def log_activity(self, profile_id, action, platform="", url="", title="",
                     status="ok", duration_s=None, error=None):
        """
        Ghi 1 dòng lịch sử hoạt động (đã xem video / đọc bài / tạo alert...).
        Sprint 2: thêm status ('ok'/'error'), duration_s (giây), error (text khi fail) —
        đều optional, hành vi cũ (không truyền) giữ nguyên.
        Best-effort: MỌI lỗi DB chỉ in cảnh báo, KHÔNG được ném lên phá workflow bot.
        Trả về True nếu ghi thành công.
        """
        if not profile_id:
            return False
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            now_str = datetime.datetime.now().isoformat(timespec="seconds")
            cursor.execute(
                "INSERT INTO activity_history (profile_id, action, platform, url, title, created_at, "
                "status, duration_s, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (profile_id, (action or "").strip(), (platform or "").strip(),
                 (url or "").strip(), (title or "").strip()[:300], now_str,
                 (status or "ok").strip(), duration_s, (error or "")[:500] or None),
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            _say(f"[!] log_activity lỗi (bỏ qua, không ảnh hưởng bot): {e}")
            return False

    def get_activity_summary(self, profile_id=None, days=7):
        """
        Tổng hợp hoạt động gần `days` ngày (mặc định 7) để báo cáo.
        profile_id=None -> gộp mọi profile. Trả về list dict:
            {profile_id, action, platform, count, last_at,
             errors, avg_duration_s, total_duration_s}
        v1.2.7: +3 cột aggregate (errors/avg/total duration) từ data status/duration_s
        mà v1.2.6 đã wire. Cột cũ NULL (row trước wiring) -> AVG/SUM bỏ qua tự nhiên
        (SQLite aggregate bỏ NULL), COUNT(error) chỉ đếm row status='error'.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        since = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat(timespec="seconds")
        select = (
            "SELECT profile_id, action, platform, COUNT(*) AS n, MAX(created_at), "
            "SUM(CASE WHEN status='error' THEN 1 ELSE 0 END), "
            "AVG(duration_s), SUM(duration_s) "
            "FROM activity_history "
        )
        if profile_id:
            cursor.execute(
                select + "WHERE profile_id=? AND created_at>=? "
                "GROUP BY profile_id, action, platform ORDER BY n DESC",
                (profile_id, since),
            )
        else:
            cursor.execute(
                select + "WHERE created_at>=? "
                "GROUP BY profile_id, action, platform ORDER BY n DESC",
                (since,),
            )
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "profile_id": r[0], "action": r[1], "platform": r[2],
                "count": r[3], "last_at": r[4],
                "errors": r[5] or 0,
                "avg_duration_s": r[6], "total_duration_s": r[7],
            }
            for r in rows
        ]

    def get_activity_rows(self, profile_id=None, days=7):
        """
        Sprint 2: trả dòng thô activity_history gần `days` ngày (cho Export CSV).
        profile_id=None -> mọi profile. Trả về list dict theo thứ tự thời gian tăng dần.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        since = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat(timespec="seconds")
        if profile_id:
            cursor.execute(
                "SELECT profile_id, action, platform, url, title, created_at, status, duration_s, error "
                "FROM activity_history WHERE profile_id=? AND created_at>=? ORDER BY id",
                (profile_id, since),
            )
        else:
            cursor.execute(
                "SELECT profile_id, action, platform, url, title, created_at, status, duration_s, error "
                "FROM activity_history WHERE created_at>=? ORDER BY id",
                (since,),
            )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

    # ================= BẢNG TÀI KHOẢN (Sprint 2) =================
    def get_profile_dashboard_info(self):
        """
        Tổng hợp dữ liệu mới nhất theo profile cho 'Bảng tài khoản' (UI):
            profile_id -> {last_action, last_at, last_alert, last_sub}
        - last_action/last_at: hành động cuối trong activity_history (id lớn nhất mỗi profile)
        - last_alert: created_at alert gần nhất (alert_history) — suy hạn tạo alert mới (7 ngày)
        - last_sub: last_sub_date (subscriptions) — suy hạn Sub hôm nay
        Best-effort: lỗi chỉ in cảnh báo, trả về phần đã đọc được.
        """
        info = {}
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "SELECT profile_id, action, created_at, status, error FROM activity_history "
                    "WHERE id IN (SELECT MAX(id) FROM activity_history GROUP BY profile_id)"
                )
                for pid, action, at, status, error in cursor.fetchall():
                    d = info.setdefault(pid, {})
                    d["last_action"] = action
                    d["last_at"] = at
                    d["last_status"] = status  # v1.2.7: 'ok'/'error'/None (row cũ trước wiring)
                    d["last_error"] = error
            except Exception:
                pass  # bảng chưa tồn tại / DB trống
            try:
                cursor.execute("SELECT profile_id, MAX(created_at) FROM alert_history GROUP BY profile_id")
                for pid, at in cursor.fetchall():
                    info.setdefault(pid, {})["last_alert"] = at
            except Exception:
                pass
            try:
                cursor.execute("SELECT profile_id, last_sub_date FROM subscriptions")
                for pid, d in cursor.fetchall():
                    info.setdefault(pid, {})["last_sub"] = d
            except Exception:
                pass
            conn.close()
        except Exception as e:
            _say(f"[!] get_profile_dashboard_info lỗi (bỏ qua): {e}")
        return info

    # ================= MỐC NUÔI ACC 7 NGÀY (v1.3.5) =================
    def set_profile_start_date(self, profile_id, date_str):
        """
        Đặt/cập nhật NGÀY BẮT ĐẦU ngâm cho profile (định dạng 'YYYY-MM-DD').
        Người vận hành tự khai trên app (dialog Mốc nuôi acc) — quy ước Ngày 1 = Giai đoạn 0.
        v1.5.0: KHÔNG dùng INSERT OR REPLACE nữa (sẽ xoá trắng mail_date/phase_override/niche/note
        của các cột mới) — UPDATE trước, chỉ INSERT khi dòng chưa tồn tại.
        Best-effort: lỗi chỉ in cảnh báo, trả về False.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            now_str = datetime.datetime.now().isoformat(timespec="seconds")
            cur = conn.execute(
                "UPDATE profile_timeline SET start_date=?, updated_at=? WHERE profile_id=?",
                (date_str, now_str, profile_id),
            )
            if cur.rowcount == 0:
                conn.execute(
                    "INSERT INTO profile_timeline (profile_id, start_date, updated_at) VALUES (?, ?, ?)",
                    (profile_id, date_str, now_str),
                )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            _say(f"[!] set_profile_start_date lỗi (bỏ qua): {e}")
            return False

    def get_profile_start_dates(self):
        """{profile_id: 'YYYY-MM-DD'} — mọi profile đã đặt ngày bắt đầu. Lỗi -> {}."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute("SELECT profile_id, start_date FROM profile_timeline")
            out = {r[0]: r[1] for r in cursor.fetchall()}
            conn.close()
            return out
        except Exception as e:
            _say(f"[!] get_profile_start_dates lỗi (bỏ qua): {e}")
            return {}

    def milestone_notified(self, profile_id, milestone):
        """True nếu mốc này của profile ĐÃ từng được popup thông báo — chống spam mỗi lần mở app."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute(
                "SELECT 1 FROM milestone_history WHERE profile_id=? AND milestone=? LIMIT 1",
                (profile_id, milestone),
            )
            found = cursor.fetchone() is not None
            conn.close()
            return found
        except Exception:
            return False

    def log_milestone(self, profile_id, milestone):
        """Ghi 1 dòng lịch sử thông báo mốc (alert-history riêng cho timeline — không lẫn alert_history)."""
        try:
            conn = sqlite3.connect(self.db_path)
            now_str = datetime.datetime.now().isoformat(timespec="seconds")
            conn.execute(
                "INSERT INTO milestone_history (profile_id, milestone, notified_at) VALUES (?, ?, ?)",
                (profile_id, milestone, now_str),
            )
            conn.commit()
            conn.close()
            _say(f"[+] Đã ghi log Database: Profile {profile_id} tới mốc '{milestone}' lúc {now_str}.")
        except Exception as e:
            _say(f"[!] log_milestone lỗi (bỏ qua): {e}")

    # ================= GIAI ĐOẠN NGÂM S0..S5 (v1.5.0) =================
    def set_profile_mail_date(self, profile_id, date_str):
        """
        Đặt NGÀY LOGIN GMAIL ĐẦU TIÊN ('YYYY-MM-DD') — mốc khởi động đồng hồ Hagrid 7 ngày.
        date_str rỗng/None = xoá mốc (profile quay về đồng hồ A / S0).
        Best-effort: lỗi chỉ in cảnh báo, trả về False.
        """
        try:
            value = date_str or None
            conn = sqlite3.connect(self.db_path)
            now_str = datetime.datetime.now().isoformat(timespec="seconds")
            cur = conn.execute(
                "UPDATE profile_timeline SET mail_date=?, updated_at=? WHERE profile_id=?",
                (value, now_str, profile_id),
            )
            if cur.rowcount == 0:
                conn.execute(
                    "INSERT INTO profile_timeline (profile_id, mail_date, updated_at) "
                    "VALUES (?, ?, ?)",
                    (profile_id, value, now_str),
                )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            _say(f"[!] set_profile_mail_date lỗi (bỏ qua): {e}")
            return False

    def set_profile_stage_meta(self, profile_id, phase_override=None, niche=None,
                               note=None, clear_fields=()):
        """
        Cập nhật các trường phụ của 1 profile: phase_override / niche / note.
        Chỉ ghi trường nào khác None (clear_fields = danh sách trường cần xoá trắng).
        Best-effort: lỗi chỉ in cảnh báo, trả về False.
        """
        sets, params = [], []
        for col, val in (("phase_override", phase_override), ("niche", niche), ("note", note)):
            if col in clear_fields:
                sets.append(f"{col}=?")
                params.append(None)
            elif val is not None:
                if col == "phase_override" and val not in VALID_PHASES:
                    continue
                sets.append(f"{col}=?")
                params.append(val)
        if not sets:
            return True
        try:
            now_str = datetime.datetime.now().isoformat(timespec="seconds")
            sets.append("updated_at=?")
            params.append(now_str)
            params.append(profile_id)
            conn = sqlite3.connect(self.db_path)
            cur = conn.execute(
                f"UPDATE profile_timeline SET {', '.join(sets)} WHERE profile_id=?", params
            )
            if cur.rowcount == 0:
                conn.execute(
                    "INSERT INTO profile_timeline (profile_id, updated_at) VALUES (?, ?)",
                    (profile_id, now_str),
                )
                cols, vals = [], []
                for col, val in (("phase_override", phase_override), ("niche", niche),
                                 ("note", note)):
                    if col in clear_fields:
                        continue
                    if val is not None and (col != "phase_override" or val in VALID_PHASES):
                        cols.append(col)
                        vals.append(val)
                if cols:
                    conn.execute(
                        f"UPDATE profile_timeline SET {', '.join(c + '=?' for c in cols)} "
                        "WHERE profile_id=?", vals + [profile_id]
                    )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            _say(f"[!] set_profile_stage_meta lỗi (bỏ qua): {e}")
            return False

    def get_profile_stage_rows(self):
        """
        {profile_id: {start_date, mail_date, phase_override, niche, note}} cho MỌI profile
        có dòng trong profile_timeline. Lỗi -> {}.
        """
        out = {}
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute(
                "SELECT profile_id, start_date, mail_date, phase_override, niche, note "
                "FROM profile_timeline"
            )
            for pid, sd, md, po, ni, no in cursor.fetchall():
                out[pid] = {"start_date": sd or "", "mail_date": md or "",
                            "phase_override": po or "", "niche": ni or "", "note": no or ""}
            conn.close()
        except Exception as e:
            _say(f"[!] get_profile_stage_rows lỗi (bỏ qua): {e}")
        return out

    def log_stage_change(self, profile_id, stage, source="auto", note=None):
        """
        Ghi 1 dòng vào 'stage_history' (sổ append-only). CHỈ ghi khi giai đoạn KHÁC lần ghi cuối
        của profile đó (chống rác khi auto-tính lại mỗi lần mở app).
        source: 'auto' | 'manual' | 'backfill'. Trả True nếu có ghi, False nếu bỏ qua/lỗi.
        """
        if not profile_id or not stage:
            return False
        try:
            conn = sqlite3.connect(self.db_path)
            row = conn.execute(
                "SELECT stage FROM stage_history WHERE profile_id=? ORDER BY id DESC LIMIT 1",
                (profile_id,),
            ).fetchone()
            if row and row[0] == stage:
                conn.close()
                return False
            now_str = datetime.datetime.now().isoformat(timespec="seconds")
            conn.execute(
                "INSERT INTO stage_history (profile_id, stage, entered_at, source, note) "
                "VALUES (?, ?, ?, ?, ?)",
                (profile_id, stage, now_str, source or "auto", note),
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            _say(f"[!] log_stage_change lỗi (bỏ qua): {e}")
            return False

    def get_stage_history(self, profile_id, limit=50):
        """[{'stage','entered_at','source','note'}, ...] mới nhất trước. Lỗi -> []."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute(
                "SELECT stage, entered_at, source, note FROM stage_history "
                "WHERE profile_id=? ORDER BY id DESC LIMIT ?",
                (profile_id, int(limit)),
            )
            out = [{"stage": r[0], "entered_at": r[1], "source": r[2], "note": r[3]}
                   for r in cursor.fetchall()]
            conn.close()
            return out
        except Exception as e:
            _say(f"[!] get_stage_history lỗi (bỏ qua): {e}")
            return []

    def get_stage_overview(self, today=None):
        """
        Bảng giai đoạn cho TOÀN BỘ profile có dòng timeline:
            pid -> {stage, stage_name, sheet_label, clock, day_no, day_total, day_label,
                    days_left, overdue, offset, start_date, mail_date, phase_override,
                    niche, note, suggested_phase, effective_phase, phase_forced,
                    warnings: [str], evidence: {has_alert, has_yt, last_action, last_activity}}
        `effective_phase` = phase_override (nếu hợp lệ) ngược lại suggested_phase.
        Best-effort: lỗi -> {}.
        """
        today = today or datetime.date.today()
        out = {}
        try:
            rows = self.get_profile_stage_rows()
            if not rows:
                return {}
            conn = sqlite3.connect(self.db_path)
            ev = {}

            def _fill(sql, key):
                try:
                    for pid, val in conn.execute(sql).fetchall():
                        ev.setdefault(pid, {})[key] = val
                except Exception:
                    pass

            _fill("SELECT profile_id, MAX(created_at) FROM activity_history GROUP BY profile_id",
                  "last_activity")
            _fill("SELECT profile_id, MAX(created_at) FROM alert_history GROUP BY profile_id",
                  "last_alert")
            _fill("SELECT profile_id, MAX(created_at) FROM activity_history "
                  "WHERE platform='YouTube' OR action LIKE '%youtube%' OR action='watch_video' "
                  "GROUP BY profile_id", "last_yt")
            conn.close()
            for pid, meta in rows.items():
                info = compute_stage(meta.get("start_date"), meta.get("mail_date"), today)
                info.update(meta)
                sug = suggested_phase(info["stage"])
                forced = (meta.get("phase_override") or "").strip()
                if forced in VALID_PHASES:
                    info["effective_phase"] = forced
                    info["phase_forced"] = True
                else:
                    info["effective_phase"] = sug
                    info["phase_forced"] = False
                info["suggested_phase"] = sug
                e = ev.get(pid, {})
                info["evidence"] = {
                    "has_alert": bool(e.get("last_alert")),
                    "has_yt": bool(e.get("last_yt")),
                    "last_action": e.get("last_activity"),
                    "last_activity": e.get("last_activity"),
                }
                info["warnings"] = self._stage_warnings(info, today)
                out[pid] = info
        except Exception as e:
            _say(f"[!] get_stage_overview lỗi (bỏ qua): {e}")
        return out

    @staticmethod
    def _stage_warnings(info, today):
        """Danh sách cảnh báo vận hành cho 1 profile (dùng cho cột 'Cảnh báo' + badge)."""
        warns = []
        stage = info.get("stage") or ""
        if not stage:
            warns.append("chưa đặt ngày bắt đầu")
            return warns
        if info.get("overdue"):
            if info.get("clock") == "A":
                warns.append("quá 4 ngày vẫn chưa có mail — cần login Gmail để mở đồng hồ Hagrid")
            else:
                warns.append("ngày mail ở tương lai — kiểm tra lại")
        sd = _parse_iso_date(info.get("start_date"))
        if not info.get("mail_date") and sd is not None:
            waited = (today - sd).days
            if waited > 7:
                warns.append(f"đã {waited} ngày không có mail — acc đang bị kẹt ở S0")
        if stage in ("S3", "S4", "S5"):
            ev = info.get("evidence") or {}
            if not ev.get("has_yt"):
                warns.append("đã tới giai đoạn YouTube nhưng chưa có hoạt động YouTube nào")
        if stage == "S5" and not info.get("evidence", {}).get("last_alert"):
            pass  # sub check cần DB riêng — để UI tự bổ sung nếu cần
        return warns

    def backfill_stage_tracking(self):
        """
        v1.5.0 — điền dữ liệu giai đoạn cho các profile ĐÃ có dấu vết chạy nhưng chưa có timeline.
        Quy tắc (an toàn, không ghi đè dữ liệu người vận hành đã nhập):
            1. Chưa có start_date + có activity_history -> start_date = MIN(created_at).date()
            2. Chưa có mail_date + có alert_history      -> CHỈ trả về gợi ý (không tự ghi)
            3. Mọi profile có start_date -> ghi 1 dòng stage_history source='backfill' nếu trống
        Trả về {'filled_start': n, 'logged': n, 'mail_hints': {pid: 'YYYY-MM-DD'}}.
        """
        result = {"filled_start": 0, "logged": 0, "mail_hints": {}}
        try:
            rows = self.get_profile_stage_rows()
            conn = sqlite3.connect(self.db_path)
            first_act = dict(conn.execute(
                "SELECT profile_id, MIN(created_at) FROM activity_history GROUP BY profile_id"
            ).fetchall())
            first_alert = dict(conn.execute(
                "SELECT profile_id, MIN(created_at) FROM alert_history GROUP BY profile_id"
            ).fetchall())
            conn.close()
            for pid, first in first_act.items():
                d = _parse_iso_date(str(first or "")[:10])
                if d is None:
                    continue
                meta = rows.get(pid) or {}
                if not (meta.get("start_date") or "").strip():
                    if self.set_profile_start_date(pid, d.isoformat()):
                        result["filled_start"] += 1
                        rows.setdefault(pid, {})["start_date"] = d.isoformat()
            for pid, first in first_alert.items():
                meta = rows.get(pid) or {}
                if not (meta.get("mail_date") or "").strip():
                    d = _parse_iso_date(str(first or "")[:10])
                    if d is not None:
                        result["mail_hints"][pid] = d.isoformat()
            for pid, meta in rows.items():
                info = compute_stage(meta.get("start_date"), meta.get("mail_date"))
                if info["stage"] and self.log_stage_change(
                        pid, info["stage"], source="backfill",
                        note="tự điền từ dữ liệu chạy cũ"):
                    result["logged"] += 1
        except Exception as e:
            _say(f"[!] backfill_stage_tracking lỗi (bỏ qua): {e}")
        return result

    # ================= THỜI GIAN NGÂM THEO CHU TRÌNH (v1.4.0) =================
    def log_cycle(self, profile_id, started_at, finished_at, duration_s, status,
                  actions=0, phase="", error=None, target_s=None):
        """
        Ghi 1 chu trình ngâm của 1 profile (UI worker gọi ở finally — kể cả lỗi/dừng giữa
        chừng). status: 'ok' | 'error' | 'stopped'. Best-effort: lỗi chỉ in cảnh báo.
        v1.4.1: target_s = mục tiêu (giây) của RIÊNG vòng này (random mỗi vòng); None = không đặt.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT INTO cycle_history (profile_id, started_at, finished_at, duration_s,"
                " status, actions, phase, error, target_s) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (profile_id, started_at, finished_at, duration_s, status,
                 actions, phase, error,
                 (float(target_s) if target_s else None)),
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            _say(f"[!] log_cycle lỗi (bỏ qua, không ảnh hưởng bot): {e}")
            return False

    def get_cycle_summary(self, profile_id=None, days=30, target_s=0):
        """
        Tổng hợp thời gian ngâm theo profile trong `days` ngày gần nhất (theo giờ máy):
            pid -> {cycles, total_s, avg_s, ok, error, stopped, over, last_at,
                    last_status, last_error, last_duration_s, last_target_s}
        Mỗi cột 'over' đếm vòng có duration_s VƯỢT mục tiêu của CHÍNH vòng đó (cột target_s,
        v1.4.1). Vòng cũ chưa ghi target_s (NULL) thì dùng `target_s` tham số làm mặc định
        (0 = không đếm). Best-effort: lỗi -> {} (bảng chưa tồn tại / DB trống cũng im lặng).
        """
        out = {}
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            where = "WHERE finished_at >= datetime('now','localtime', ?)"
            params = [f"-{int(days)} days"]
            if profile_id:
                where += " AND profile_id = ?"
                params.append(profile_id)
            # v1.4.1: 'over' đếm vòng vượt CHÍNH mốc của nó (target_s). Vòng cũ NULL mà không
            # có mốc mặc định (global_target=0) -> KHÔNG tính (tránh 'duration >= 0' luôn đúng).
            global_target = int(target_s) if (target_s and target_s > 0) else 0
            over_expr = "(COALESCE(target_s, ?) > 0 AND duration_s >= COALESCE(target_s, ?))"
            sel_params = [global_target, global_target] + params
            try:
                cursor.execute(
                    "SELECT profile_id, COUNT(*), SUM(duration_s), AVG(duration_s),"
                    " SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END),"
                    " SUM(CASE WHEN status='error' THEN 1 ELSE 0 END),"
                    " SUM(CASE WHEN status='stopped' THEN 1 ELSE 0 END),"
                    " SUM(CASE WHEN " + over_expr + " THEN 1 ELSE 0 END),"
                    " MAX(finished_at) FROM cycle_history " + where + " GROUP BY profile_id",
                    sel_params,
                )
                for pid, cycles, total_s, avg_s, ok, err, stop, over, last_at in cursor.fetchall():
                    out[pid] = {"cycles": cycles, "total_s": total_s or 0.0,
                                "avg_s": avg_s, "ok": ok, "error": err,
                                "stopped": stop, "over": over, "last_at": last_at}
            except Exception:
                pass  # bảng chưa có / DB trống
            try:
                cursor.execute(
                    "SELECT profile_id, status, error, duration_s, target_s FROM cycle_history WHERE id IN ("
                    "SELECT MAX(id) FROM cycle_history " + where + " GROUP BY profile_id)",
                    params,
                )
                for pid, st, er, dur, tgt in cursor.fetchall():
                    if pid in out:
                        out[pid]["last_status"] = st
                        out[pid]["last_error"] = er
                        out[pid]["last_duration_s"] = dur
                        out[pid]["last_target_s"] = tgt  # v1.4.1: mục tiêu riêng của vòng cuối
            except Exception:
                pass
            conn.close()
        except Exception as e:
            _say(f"[!] get_cycle_summary lỗi (bỏ qua): {e}")
        return out

    def get_cycle_rows(self, profile_id, days=90, limit=200):
        """Chi tiết chu trình của 1 profile (mới nhất trước) — dialog Thời gian ngâm.
        [{started_at, finished_at, duration_s, status, actions, phase, error, target_s}]. Lỗi -> []."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute(
                "SELECT started_at, finished_at, duration_s, status, actions, phase, error, target_s"
                " FROM cycle_history WHERE profile_id=?"
                " AND finished_at >= datetime('now','localtime',?)"
                " ORDER BY id DESC LIMIT ?",
                (profile_id, f"-{int(days)} days", int(limit)),
            )
            rows = [dict(zip(("started_at", "finished_at", "duration_s", "status",
                              "actions", "phase", "error", "target_s"), r)) for r in cursor.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            _say(f"[!] get_cycle_rows lỗi (bỏ qua): {e}")
            return []

    def get_cycle_lifetime_stats(self):
        """v1.4.9: thống kê TRỌN ĐỜI mỗi profile từ cycle_history (không lọc cửa sổ ngày),
        cho Board thời lượng. pid -> {cycles_all, total_all_s, today_s, actions_all,
                                      first_at, days_active, last_status, last_error,
                                      last_duration_s, last_at}
            today_s     = tổng giây NGÂM HÔM NAY (theo ngày giờ máy)
            actions_all = SỐ HÀNH ĐỘNG lũy kế (tổng cột actions)
            first_at    = lần chạy đầu tiên (MIN started_at)
            days_active = số NGÀY KHÁC CÓ chạy (COUNT DISTINCT date(started_at))
        Best-effort: bảng chưa có / DB trống -> {}.
        """
        out = {}
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute(
                "SELECT profile_id, COUNT(*), SUM(duration_s),"
                " SUM(CASE WHEN date(finished_at) = date('now','localtime')"
                "     THEN duration_s ELSE 0 END),"
                " SUM(COALESCE(actions, 0)), MIN(started_at),"
                " COUNT(DISTINCT date(started_at))"
                " FROM cycle_history GROUP BY profile_id",
            )
            for pid, cycles, total_s, today_s, acts, first_at, days_active in cursor.fetchall():
                out[pid] = {"cycles_all": cycles or 0,
                            "total_all_s": total_s or 0.0,
                            "today_s": today_s or 0.0,
                            "actions_all": acts or 0,
                            "first_at": first_at,
                            "days_active": days_active or 0}
            # v1.4.9: row CUỐI MỌI THỜI — board vẫn hiện "Kết quả"/"Xong lúc" cho profile
            # có vòng nằm NGOÀI cửa sổ ngày đang chọn (không bị hiểu nhầm là chưa chạy).
            cursor = conn.execute(
                "SELECT profile_id, status, error, duration_s, finished_at FROM cycle_history"
                " WHERE id IN (SELECT MAX(id) FROM cycle_history GROUP BY profile_id)",
            )
            for pid, status, err, dur, fin in cursor.fetchall():
                if pid in out:
                    out[pid]["last_status"] = status or ""
                    out[pid]["last_error"] = err or ""
                    out[pid]["last_duration_s"] = dur
                    out[pid]["last_at"] = fin or ""
            conn.close()
        except Exception as e:
            _say(f"[!] get_cycle_lifetime_stats lỗi (bỏ qua): {e}")
        return out

    def get_last_cycle_targets(self, days=30):
        """v1.4.1: mục tiêu (giây) của VÒNG MỚI NHẤT mỗi profile trong `days` ngày:
        pid -> target_s (float). Dùng cho Bảng tài khoản (⏰ so với vòng cuối). Lỗi -> {}."""
        out = {}
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.execute(
                "SELECT profile_id, target_s FROM cycle_history WHERE id IN ("
                "SELECT MAX(id) FROM cycle_history"
                " WHERE finished_at >= datetime('now','localtime',?)"
                " GROUP BY profile_id) AND target_s IS NOT NULL",
                (f"-{int(days)} days",),
            )
            for pid, tgt in cursor.fetchall():
                out[pid] = tgt
            conn.close()
        except Exception as e:
            _say(f"[!] get_last_cycle_targets lỗi (bỏ qua): {e}")
        return out

    def get_today_seconds(self, profile_ids=None):
        """v1.5.3: tổng số giây ĐÃ NGÂM HÔM NAY của từng profile (hạn mức phút/ngày).
        pid -> float. `profile_ids` = None -> mọi profile có row hôm nay.
        Best-effort: bảng chưa có / DB trống -> {}. Không tạo row, chỉ đọc."""
        out = {}
        try:
            conn = sqlite3.connect(self.db_path)
            sql = ("SELECT profile_id, COALESCE(SUM(duration_s), 0) FROM cycle_history"
                   " WHERE date(finished_at) = date('now','localtime')")
            params = []
            if profile_ids:
                pids = [p for p in profile_ids if p]
                if not pids:
                    conn.close()
                    return {}
                sql += " AND profile_id IN (%s)" % ",".join("?" * len(pids))
                params.extend(pids)
            sql += " GROUP BY profile_id"
            for pid, secs in conn.execute(sql, params).fetchall():
                out[pid] = float(secs or 0.0)
            conn.close()
        except Exception as e:
            _say(f"[!] get_today_seconds lỗi (bỏ qua): {e}")
        return out
