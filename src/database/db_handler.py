import sqlite3
import datetime
import os

class DatabaseHandler:
    def __init__(self, db_path="data/agent_logs.db"):
        """
        Khởi tạo kết nối tới database SQLite.
        Nếu thư mục 'data' chưa có, sẽ tự động tạo.
        """
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._create_tables()

    def _create_tables(self):
        """
        Tạo bảng 'subscriptions' để lưu lịch sử nhấn nút.
        Chỉ lưu ID Profile và mốc thời gian thực hiện Sub gần nhất.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                profile_id TEXT PRIMARY KEY,
                last_sub_date TEXT
            )
        ''')
        conn.commit()
        conn.close()

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