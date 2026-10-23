"""v1.4.8 — Tiện ích quản lý API KEY có cổng mật khẩu, khỏi phải sửa .env tay.

Nguyên tắc:
- Key VẪN lưu trong file `.env` gốc repo (đường dẫn qua src.paths.env_path()) ->
  `agent/brain_manager.py` (dotenv + os.getenv) KHÔNG cần sửa gì.
- Mỗi lần ghi key: cập nhật os.environ NGAY trong process -> brain mới dùng được
  luôn, không cần mở lại app.
- Cổng mật khẩu: stdlib hashlib PBKDF2 (máy không có cryptography/keyring).
  Mật khẩu khởi điểm = DEFAULT_PASSWORD; lần xác minh đúng đầu tiên sẽ lưu
  salt+hash vào app_config.json (data/, đã gitignore). "Đổi mật khẩu" ghi hash mới.
- Ghi file atomic (tmp -> os.replace), giữ nguyên dòng/comment lạ trong .env.

Mọi hàm best-effort: lỗi I/O trả False/[] + in log `[!]`, KHÔNG bao giờ ném
làm chết GUI.
"""
import hashlib
import io
import os
import re
import secrets
import threading

# Mật khẩu khởi điểm của tiện ích (user đổi bằng nút "Đổi mật khẩu" trong tool).
DEFAULT_PASSWORD = "gpm123"

# Các key AI brain_manager hay dùng -> gợi ý sẵn trong dialog.
KNOWN_KEYS = [
    ("GEMINI_API_KEY", "Google Gemini (brain gemini)"),
    ("OPENAI_API_KEY", "OpenAI (brain openai)"),
    ("QWEN_API_KEY", "Qwen DashScope (brain qwen-max / qwen-flash)"),
    ("DASHSCOPE_API_KEY", "Qwen - alias cũ (nếu QWEN_API_KEY trống)"),
    ("TELEGRAM_BOT_TOKEN", "Bot Telegram đổi mật khẩu từ xa (v1.5.4)"),
]

_PBKDF2_ROUNDS = 200_000
_lock = threading.Lock()

_KEY_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


# ---------------------------------------------------------------- đường dẫn .env
def env_path():
    """File .env gốc repo (frozen-aware). Fallback: cwd/.env nếu src.paths lỗi."""
    try:
        from src.paths import env_path as _resolve
        return _resolve()
    except Exception:
        return os.path.join(os.getcwd(), ".env")


# ---------------------------------------------------------------- endpoint đi kèm key
def endpoint_name(name):
    """Tên biến môi trường 'đi kèm' chứa endpoint của một key (v1.5.6).

    Quy ước: GEMINI_API_KEY -> GEMINI_API_KEY_ENDPOINT.
    Có biến này (không rỗng) -> mọi chỗ dùng key gọi theo cổng tự đặt;
    bỏ trống -> giữ nguyên cổng chính mặc định của thư viện / hardcoded.
    """
    return f"{(name or '').strip().upper()}_ENDPOINT"


def is_endpoint_key(name):
    """True nếu tên key là biến endpoint đi kèm (không hiển thị thành dòng riêng)."""
    return (name or "").strip().upper().endswith("_ENDPOINT")


# ---------------------------------------------------------------- đọc/ghi .env
def _read_text(path):
    try:
        with io.open(path, "r", encoding="utf-8-sig", newline="") as f:
            return f.read()
    except FileNotFoundError:
        return ""
    except Exception as e:
        print(f"[!] api_vault đọc {os.path.basename(path)} lỗi (bỏ qua): {e}")
        return ""


def _write_text(path, text):
    """Ghi atomic: file tạm cùng thư mục -> os.replace."""
    tmp = path + ".tmp"
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with io.open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, path)
        return True
    except Exception as e:
        print(f"[!] api_vault ghi {os.path.basename(path)} lỗi: {e}")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False


def _split_keep_newlines(text):
    """Tách dòng GIỮ nguyên ký tự xuống dòng của từng dòng (giữ CRLF/LF gốc)."""
    lines, buf = [], []
    for ch in text:
        buf.append(ch)
        if ch == "\n":
            lines.append("".join(buf))
            buf = []
    if buf:
        lines.append("".join(buf))
    return lines


def list_keys(path=None):
    """-> [(key, value)] theo thứ tự trong file (bỏ comment/dòng rỗng)."""
    path = path or env_path()
    out = []
    for line in _read_text(path).splitlines():
        m = _KEY_RE.match(line)
        if not m:
            continue
        key = m.group(1)
        val = line.split("=", 1)[1].strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        out.append((key, val))
    return out


def get_key(name, path=None):
    for k, v in list_keys(path):
        if k == name:
            return v
    return os.environ.get(name, "")


def get_endpoint(name, path=None):
    """Endpoint tự đặt của một key ('' = dùng cổng chính mặc định). v1.5.6."""
    return (get_key(endpoint_name(name), path) or "").strip()


def set_key(name, value, path=None):
    """Cập nhật (hoặc thêm mới) KEY=value vào .env, đồng bộ os.environ. -> True/False."""
    name = (name or "").strip()
    if not _KEY_RE.match(f"{name}="):
        print(f"[!] api_vault: tên key không hợp lệ: {name!r}")
        return False
    path = path or env_path()
    with _lock:
        text = _read_text(path)
        lines = _split_keep_newlines(text)
        if lines and not lines[-1].endswith("\n"):
            lines[-1] = lines[-1] + ("\r\n" if "\r\n" in text else "\n")
        new_line = f"{name}={value}"
        replaced = False
        for i, line in enumerate(lines):
            m = _KEY_RE.match(line)
            if m and m.group(1) == name:
                nl = "\r\n" if line.endswith("\r\n") else "\n"
                lines[i] = new_line + nl
                replaced = True
                break
        if not replaced:
            lines.append(new_line + ("\r\n" if "\r\n" in text else "\n"))
        if not _write_text(path, "".join(lines)):
            return False
    os.environ[name] = value
    return True


def delete_key(name, path=None):
    """Xóa mọi dòng KEY=... khỏi .env + pop os.environ. -> True/False (True kể cả khi không có)."""
    name = (name or "").strip()
    path = path or env_path()
    with _lock:
        text = _read_text(path)
        if not text:
            os.environ.pop(name, None)
            return True
        kept = []
        removed = 0
        for line in _split_keep_newlines(text):
            m = _KEY_RE.match(line)
            if m and m.group(1) == name:
                removed += 1
                continue
            kept.append(line)
        if removed and not _write_text(path, "".join(kept)):
            return False
    os.environ.pop(name, None)
    return True


def delete_endpoint(name, path=None):
    """Gỡ endpoint tự đặt của một key -> acc/brain quay về cổng chính. v1.5.6."""
    return delete_key(endpoint_name(name), path)


def sync_env_into_process(path=None):
    """Nạp mọi key trong .env vào os.environ (gọi lúc mở app để EXE/source đều như nhau)."""
    n = 0
    for k, v in list_keys(path):
        if v:
            os.environ[k] = v
            n += 1
    return n


def known_keys_with_endpoints():
    """[(tên key, mô tả, tên biến endpoint của nó)] — để UI khỏi liệt kê biến
    endpoint như một key độc lập. v1.5.6."""
    return [(k, d, endpoint_name(k)) for k, d in KNOWN_KEYS]


def mask(value):
    """Che key cho hiển thị: 4 đầu + ... + 4 cuối (key ngắn -> che hết)."""
    value = value or ""
    if len(value) <= 8:
        return "•" * len(value) if value else ""
    return f"{value[:4]}…{'•' * 6}…{value[-4:]}"


# ---------------------------------------------------------------- cổng mật khẩu
def _config_io():
    from src import app_config
    return app_config


def _hash_password(password, salt_hex):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), _PBKDF2_ROUNDS
    ).hex()


def has_custom_password():
    """True khi app_config đã có salt+hash (đã kích hoạt mật khẩu riêng)."""
    try:
        cfg = _config_io().load_config()
        return bool(cfg.get("api_gate_salt") and cfg.get("api_gate_hash"))
    except Exception:
        return False


def check_password(password):
    """Xác minh mật khẩu tiện ích.

    - Chưa đổi mật khẩu (config trống hash): khớp DEFAULT_PASSWORD -> lưu salt+hash
      của chính nó vào config (kích hoạt chế độ "nhập mật khẩu" thật sự).
    - Đã có hash trong config: so PBKDF2 constant-time.
    """
    if not isinstance(password, str) or not password:
        return False
    try:
        cfg = _config_io().load_config()
        salt = cfg.get("api_gate_salt") or ""
        want = cfg.get("api_gate_hash") or ""
        if salt and want:
            got = _hash_password(password, salt)
            return secrets.compare_digest(got, want)
        # lần đầu: chỉ nhận mật khẩu khởi điểm, rồi "cứng hóa" bằng hash
        if not secrets.compare_digest(password, DEFAULT_PASSWORD):
            return False
        return set_password(password)
    except Exception as e:
        print(f"[!] api_vault check_password lỗi: {e}")
        return False


def set_password(new_password):
    """Đổi mật khẩu tiện ích (muộn nhất 4 ký tự). Sinh salt mới + lưu hash. -> True/False."""
    if not isinstance(new_password, str) or len(new_password) < 4:
        return False
    try:
        salt = secrets.token_hex(16)
        digest = _hash_password(new_password, salt)
        cfg = _config_io().load_config()
        cfg["api_gate_salt"] = salt
        cfg["api_gate_hash"] = digest
        return _config_io().save_config(cfg)
    except Exception as e:
        print(f"[!] api_vault set_password lỗi: {e}")
        return False
