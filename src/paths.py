"""v1.3.0 — Đường dẫn data THỐNG NHẤT cho toàn app (DB, config, logs, backup).

Vấn đề cũ (audit v1.2.9): DB/config CWD-relative, logs file-relative → chạy
source vs EXE (cwd = dist) là data nằm chỗ khác nhau; EXE còn ghi DB/config
vào dist/ và PyInstaller XÓA dist mỗi lần build => mất dữ liệu.

Quy tắc mới (KHÔNG phụ thuộc cwd):
- Chạy source:  data/ = <repo root>/data   (repo root = thư mục cha của src)
- EXE đóng gói (sys.frozen): 3 cấp trên thư mục chứa EXE:
      <repo>\\src\\dist\\GPM_Auto_Bot\\GPM_Auto_Bot.exe  ->  <repo>\\data
- Override: biến môi trường GPM_BOT_DATA_DIR = thẳng thư mục data muốn dùng.

Mọi hàm trả đường dẫn tuyệt đối; data_dir()/logs_dir()/backup_dir() tự tạo
thư mục (best-effort, im lặng khi lỗi như conventions của repo).
"""
import os
import sys

ENV_OVERRIDE = "GPM_BOT_DATA_DIR"


def repo_root():
    """Thư mục dự án (cha của src) — tính từ file này (source) hoặc từ EXE (frozen)."""
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        # <repo>\src\dist\GPM_Auto_Bot -> 3 lần dirname
        return os.path.dirname(os.path.dirname(os.path.dirname(exe_dir)))
    # src/paths.py -> src -> repo root
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ensure(path):
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    return path


def data_dir():
    """Thư mục data thống nhất (env GPM_BOT_DATA_DIR thắng nếu set)."""
    env = os.environ.get(ENV_OVERRIDE)
    base = os.path.abspath(env) if env else os.path.join(repo_root(), "data")
    return _ensure(base)


def db_path():
    return os.path.join(data_dir(), "agent_logs.db")


def config_path():
    return os.path.join(data_dir(), "app_config.json")


def logs_dir():
    return _ensure(os.path.join(data_dir(), "logs"))


def backup_dir():
    return _ensure(os.path.join(data_dir(), "backup"))


def env_path():
    """File .env gốc repo (nơi brain_manager đọc API key qua dotenv).

    Không tự tạo file — chỉ trả đường dẫn; api_vault sẽ tạo khi cần ghi.
    Override: GPM_BOT_ENV_FILE trỏ thẳng file .env khác (tiện cho test cô lập).
    """
    env = os.environ.get("GPM_BOT_ENV_FILE")
    if env:
        return os.path.abspath(env)
    return os.path.join(repo_root(), ".env")
