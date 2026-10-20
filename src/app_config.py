"""Sprint 1.1 — Persist cấu hình GUI (JSON), không đụng core vận hành.

Lưu: danh sách profile (id + tên), keywords 2 cột, browser/port/brain/phase,
threads, 2 checkbox. File: data/app_config.json (cwd-relative như DB).

Atomic: ghi file tạm -> os.replace, tránh hỏng file giữa chừng khi app bị kill.
Mọi hàm best-effort: lỗi đọc/ghi config KHÔNG bao giờ được làm app crash.
"""
import json
import os
import threading

# v1.3.0: dùng src.paths để data/ thống nhất (repo-root, frozen-aware, độc lập cwd).
# Fallback 'data/' nếu import thất bại (vd chạy file này standalone ngoài package).
try:
    from src.paths import config_path as _resolve_config_path
    CONFIG_PATH = _resolve_config_path()
    _DATA_DIR = os.path.dirname(CONFIG_PATH)
except Exception:
    _DATA_DIR = "data"
    CONFIG_PATH = os.path.join(_DATA_DIR, "app_config.json")

_lock = threading.Lock()

DEFAULTS = {
    "version": 1,
    "profiles": [],          # [{"id": uuid-str, "name": str, "selected": bool}]
    "kw_google": [],         # ["...", "..."] — mỗi dòng 1 chủ đề Google
    "kw_youtube": [],        # ["...", "..."] — dòng N khớp Google dòng N
    "browser_type": "gpm",
    "api_port": "9495",
    "brain_type": "none",
    "phase": "clean",        # key nội bộ (clean/mail/youtube) — KHÔNG lưu nhãn UI
    "threads": 4,
    "skip_youtube": False,
    "skip_random_keywords": False,
    "theme": "dark",       # v1.3.3: 'dark' | 'light' — mặc định tối như trước
    "target_cycle_minutes": 0,  # v1.4.0: mục tiêu phút cho 1 chu trình (0 = không giới hạn)
    "daily_minutes": 30,     # v1.5.3: hạn mức PHÚT/NGÀY cho mỗi acc (0 = tắt hạn mức)
    "pinned_theme": "",      # v1.5.3: ghim chủ đề cho phiên ("" = bot tự chọn trong danh sách)
    # v1.4.8: cổng mật khẩu cho tiện ích "QUẢN LÝ API KEY" (PBKDF2, salt+hash hex;
    # rỗng = chưa đổi -> tiện ích nhận mật khẩu khởi điểm api_vault.DEFAULT_PASSWORD)
    "api_gate_salt": "",
    "api_gate_hash": "",
}


def load_config():
    """Đọc config, thiếu key -> điền DEFAULTS. File hỏng/trống -> DEFAULTS."""
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            for k in DEFAULTS:
                if k in raw and isinstance(raw[k], type(DEFAULTS[k])):
                    cfg[k] = raw[k]
    except FileNotFoundError:
        pass
    except Exception:
        pass  # JSON hỏng -> im lặng dùng default (không phá app)
    return cfg


def save_config(cfg):
    """Ghi atomic (tmp -> replace). Best-effort, trả về True/False."""
    try:
        with _lock:
            os.makedirs(_DATA_DIR, exist_ok=True)
            tmp = CONFIG_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=1)
            os.replace(tmp, CONFIG_PATH)
        return True
    except Exception:
        return False
