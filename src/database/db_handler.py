import sqlite3
import datetime
import os
import shutil

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
        conn.commit()
        conn.close()
        # Sprint 2: bảo đảm schema mới (status/duration_s/error) — idempotent, tự backup trước khi đổi
        self._migrate_activity_history()
        # v1.4.1: thêm cột target_s cho DB đã tạo từ v1.4.0 — idempotent, backup trước khi đổi
        self._migrate_cycle_history()

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
            print(f"[+] Đã backup DB ({reason}) -> {dst}")
            return dst
        except Exception as e:
            print(f"[!] Backup DB lỗi (bỏ qua, không ảnh hưởng bot): {e}")
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
                print("[!] Không backup được trước migration — BỎ QUA migration an toàn.")
                conn.close()
                return
            for name, typ in missing:
                cursor.execute(f"ALTER TABLE activity_history ADD COLUMN {name} {typ}")
            conn.commit()
            conn.close()
            print(f"[+] Migration activity_history xong: thêm {', '.join(n for n, _ in missing)}")
        except Exception as e:
            print(f"[!] Migration activity_history lỗi (bỏ qua): {e}")

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
                print("[!] Không backup được trước migration cycle_history — BỎ QUA migration an toàn.")
                conn.close()
                return
            cursor.execute("ALTER TABLE cycle_history ADD COLUMN target_s REAL")
            conn.commit()
            conn.close()
            print("[+] Migration cycle_history xong: thêm target_s")
        except Exception as e:
            print(f"[!] Migration cycle_history lỗi (bỏ qua): {e}")

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
            print(f"[*] Profile {profile_id} đã hết lượt Sub hôm nay. Sẽ chuyển sang chế độ chỉ Đọc báo/Xem video.")
            return False
                
        print(f"[+] Profile {profile_id} chưa Sub hôm nay. Đủ điều kiện thực hiện kịch bản Đăng ký kênh.")
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
        print(f"[+] Đã ghi log Database: Profile {profile_id} vừa Sub thành công vào lúc {today_str}.")

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
            print(f"[*] Profile {profile_id} đã tạo alert trong {days} ngày gần nhất. Bỏ qua tạo mới.")
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
        print(f"[+] Đã ghi log Database: Profile {profile_id} vừa tạo alert '{query.strip()}' lúc {now_str}.")

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
            print(f"[!] log_activity lỗi (bỏ qua, không ảnh hưởng bot): {e}")
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
            print(f"[!] get_profile_dashboard_info lỗi (bỏ qua): {e}")
        return info

    # ================= MỐC NUÔI ACC 7 NGÀY (v1.3.5) =================
    def set_profile_start_date(self, profile_id, date_str):
        """
        Đặt/cập nhật NGÀY BẮT ĐẦU ngâm cho profile (định dạng 'YYYY-MM-DD').
        Người vận hành tự khai trên app (dialog Mốc nuôi acc) — quy ước Ngày 1 = Giai đoạn 0.
        Best-effort: lỗi chỉ in cảnh báo, trả về False.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            now_str = datetime.datetime.now().isoformat(timespec="seconds")
            conn.execute(
                "INSERT OR REPLACE INTO profile_timeline (profile_id, start_date, updated_at) "
                "VALUES (?, ?, ?)",
                (profile_id, date_str, now_str),
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"[!] set_profile_start_date lỗi (bỏ qua): {e}")
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
            print(f"[!] get_profile_start_dates lỗi (bỏ qua): {e}")
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
            print(f"[+] Đã ghi log Database: Profile {profile_id} tới mốc '{milestone}' lúc {now_str}.")
        except Exception as e:
            print(f"[!] log_milestone lỗi (bỏ qua): {e}")

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
            print(f"[!] log_cycle lỗi (bỏ qua, không ảnh hưởng bot): {e}")
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
            print(f"[!] get_cycle_summary lỗi (bỏ qua): {e}")
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
            print(f"[!] get_cycle_rows lỗi (bỏ qua): {e}")
            return []

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
            print(f"[!] get_last_cycle_targets lỗi (bỏ qua): {e}")
        return out
