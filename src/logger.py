"""Task 5 — File logging riêng theo profile.

Mỗi profile 1 file: data/logs/{profile_id}.log. Dùng được cho:
- GUI (ui_main.py): mở rộng ThreadSafeStdout -> gọi append_line(profile_id, msg) theo thread.
- CLI (main_gpm.py / main.py): wrap bằng TeeStdout (đơn luồng, tuần tự nên an toàn).

Mọi thao tác file bọc try/except: lỗi ghi log KHÔNG bao giờ được phá workflow bot.
"""
import os
import sys

# v1.3.0: data/logs qua src.paths → repo-root data/, frozen-aware, độc lập cwd
# (trước đây file-relative → src/data/logs, lệch với DB/config khi chạy EXE).
try:
    from src.paths import logs_dir as _resolve_logs_dir
    LOG_DIR = _resolve_logs_dir()
except Exception:
    LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "logs")


def _safe_name(profile_id):
    """Chsanitize profile_id thành tên file an toàn (UUID/ASCII, giữ - và _)."""
    raw = str(profile_id or "unknown")
    cleaned = "".join(c for c in raw if c.isalnum() or c in "-_")[:80]
    return cleaned or "unknown"


def profile_log_path(profile_id):
    """Trả về đường dẫn file log của profile, đảm bảo thư mục data/logs tồn tại."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except Exception:
        pass
    return os.path.join(LOG_DIR, f"{_safe_name(profile_id)}.log")


def append_line(profile_id, text):
    """Append 1 đoạn text vào file log của profile. Best-effort, im lặng khi lỗi.
    Bỏ qua nếu không có profile_id (vd log header ngoài vòng lặp CLI)."""
    if not profile_id or not text:
        return
    try:
        with open(profile_log_path(profile_id), "a", encoding="utf-8") as f:
            f.write(text)
            f.flush()
    except Exception:
        pass


class TeeStdout:
    """
    Replacement cho sys.stdout khi chạy CLI đơn luồng: mỗi print vừa ra console
    gốc (delegate) vừa được ghi vào file log của profile hiện hành.
    """

    def __init__(self, profile_id, original=None):
        self.profile_id = profile_id
        self.original = original if original is not None else sys.__stdout__

    def write(self, msg):
        try:
            if self.original is not None:
                self.original.write(msg)
        except Exception:
            pass
        append_line(self.profile_id, msg)
        return len(msg) if msg else 0

    def flush(self):
        try:
            if self.original is not None:
                self.original.flush()
        except Exception:
            pass

    def isatty(self):
        try:
            return self.original.isatty()
        except Exception:
            return False
