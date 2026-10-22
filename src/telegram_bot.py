"""v1.5.4 — Bot Telegram đổi mật khẩu cổng API từ xa (long-polling, không thêm dependency).

Mục đích: user quên/không tiện mở app vẫn đổi được mật khẩu của tiện ích
"QUẢN LÝ API KEY". Toàn bộ băm mật khẩu ỦY THÁC cho `src.api_vault`
(KHÔNG tự hash ở đây) — bot chỉ là kênh nhận lệnh từ xa.

Bảo mật:
  - Chỉ nhận update từ ĐÚNG chat_id đã cấu hình; mọi chat khác bị bỏ qua im lặng.
  - `/set MẬT_KHẨU_CŨ MẬT_KHẨU_MỚI`: phải qua `api_vault.check_password`.
  - `/reset` → bot gửi mã 6 số về chat (hiệu lực 5 phút, dùng 1 lần);
    `/confirm MÃ MẬT_KHẨU_MỚI` → đổi mật khẩu KHÔNG cần mật khẩu cũ.
  - Tham số được làm sạch: nếu user lỡ gõ `<mã>` / `"mật khẩu"` thì tự bỏ
    dấu bao quanh (bài học v1.5.5: user gõ `/confirm <683145> <abc>` và bị
    báo "Mã không đúng" chỉ vì dấu ngoặc nhọn).
  - Sai 5 lần liên tiếp → tạm khoá 10 phút (chống dò mật khẩu qua Telegram).

Nguyên tắc an toàn:
  - Không bao giờ raise ra ngoài (mọi lỗi mạng/API đều bị nuốt + log).
  - Log đi qua callback của UI nếu có; nếu không thì dùng `_say()` tự bọc
    UnicodeEncodeError vì EXE console là **cp1252** (v1.5.0 đã sập app một lần
    chỉ vì print tiếng Việt có dấu).
"""
import secrets
import sys
import threading
import time

try:
    import requests
except Exception:  # pragma: no cover - requests luôn có trong bundle
    requests = None

API_BASE = "https://api.telegram.org"
DEFAULT_POLL_TIMEOUT = 25      # giây — getUpdates long-poll
MAX_FAILS = 5                  # số lần sai liên tiếp trước khi tạm khoá
LOCK_SECONDS = 600             # 10 phút
RESET_TTL = 300                # mã /reset sống 5 phút
RESET_MAX_TRIES = 3            # nhập sai mã 3 lần -> huỷ mã
MIN_PASSWORD_LEN = 4           # khớp api_vault.set_password

CMD_HELP = (
    "Lệnh đổi mật khẩu cổng API key:\n"
    "/status — xem trạng thái\n"
    "/set MẬT_KHẨU_CŨ MẬT_KHẨU_MỚI — đổi khi còn nhớ mật khẩu cũ\n"
    "/reset — quên mật khẩu: bot gửi mã 6 số (5 phút, 1 lần)\n"
    "/confirm MÃ MẬT_KHẨU_MỚI — đổi bằng mã vừa nhận\n"
    "/cancel — huỷ mã đang chờ\n"
    "/help — xem lại hướng dẫn\n"
    f"Mật khẩu mới tối thiểu {MIN_PASSWORD_LEN} ký tự.\n"
    "Lưu ý: chỉ gõ giá trị thật, KHÔNG gõ dấu < > hay dấu ngoặc kép.\n"
    "Ví dụ đúng: /confirm 123456 matkhaumoi"
)


def _say(msg):
    """In log an toàn encoding (EXE console cp1252) — không bao giờ raise."""
    text = str(msg)
    try:
        print(text)
    except UnicodeEncodeError:
        try:
            enc = getattr(sys.stdout, "encoding", None) or "ascii"
            print(text.encode(enc, "replace").decode(enc, "replace"))
        except Exception:
            pass
    except Exception:
        pass


def _clean_arg(value):
    """Bỏ dấu bao quanh mà user hay gõ nhầm: <abc> "abc" 'abc'."""
    out = (value or "").strip()
    if len(out) >= 2:
        if (out[0], out[-1]) in (("<", ">"), ('"', '"'), ("'", "'"), ("[", "]"), ("(", ")")):
            out = out[1:-1].strip()
    return out


def _requests_http(method, url, params=None, json=None, timeout=15):
    """Transport mặc định (có thể thay bằng callable khác khi test)."""
    if requests is None:
        return {"ok": False, "description": "thieu goi requests"}
    resp = requests.request(method, url, params=params, json=json, timeout=timeout)
    try:
        data = resp.json()
    except Exception:
        return {"ok": False, "description": f"HTTP {resp.status_code}"}
    return data if isinstance(data, dict) else {"ok": False, "description": "JSON la"}


def mask_token(token):
    """Che token khi hiển thị log/UI."""
    token = str(token or "")
    if not token:
        return ""
    if len(token) <= 10:
        return "*" * len(token)
    return f"{token[:6]}…{'*' * 6}…{token[-4:]}"


def _vault():
    """Import trễ để tránh vòng import và cho phép monkeypatch khi test."""
    from src import api_vault
    return api_vault


def _safe_vault(fn_name, *args):
    """Gọi api_vault an toàn: lỗi -> None (và không bao giờ raise)."""
    try:
        return getattr(_vault(), fn_name)(*args)
    except Exception:
        return None


class TelegramPasswordBot:
    """Long-poll getUpdates trong 1 daemon thread; xử lý lệnh đổi mật khẩu."""

    def __init__(self, token, chat_id, log=None, http=None,
                 api_base=API_BASE, poll_timeout=DEFAULT_POLL_TIMEOUT,
                 on_password_changed=None):
        self.token = str(token or "").strip()
        self.chat_id = str(chat_id or "").strip()
        self.log = log
        self.http = http or _requests_http
        self.api_base = str(api_base or API_BASE).rstrip("/")
        self.poll_timeout = int(poll_timeout or DEFAULT_POLL_TIMEOUT)
        self.on_password_changed = on_password_changed

        self._stop = threading.Event()
        self._thread = None
        self._offset = 0
        self._primed = False
        self._last_error = ""
        self._started_at = 0.0

        # chống dò mật khẩu
        self._fails = 0
        self._lock_until = 0.0

        # trạng thái /reset
        self._reset_code = ""
        self._reset_expires = 0.0
        self._reset_tries = 0

    # ------------------------------------------------------------- tiện ích
    def configured(self):
        """Đủ token + chat_id để chạy chưa."""
        return bool(self.token and self.chat_id)

    def is_running(self):
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    def status_text(self):
        if self.is_running():
            state = "đang chạy"
        elif self.configured():
            state = "đã cấu hình nhưng chưa chạy"
        else:
            state = "chưa cấu hình"
        lines = [f"Bot Telegram: {state}"]
        if self.chat_id:
            lines.append(f"Chat ID khoá: {self.chat_id}")
        if self.token:
            lines.append(f"Token: {mask_token(self.token)}")
        if self._started_at:
            lines.append("Thời gian chạy: {}".format(_fmt_dur_block(time.time() - self._started_at)))
        if self._last_error:
            lines.append(f"Lỗi gần nhất: {self._last_error}")
        if self._reset_code:
            left = max(0, int(self._reset_expires - time.time()))
            lines.append(f"Đang chờ mã /confirm: còn {left}s")
        return "\n".join(lines)

    def _log(self, msg):
        text = str(msg)
        if self.log is not None:
            try:
                self.log(text)
                return
            except Exception:
                pass
        _say(text)

    # ------------------------------------------------------------- vòng chạy
    def start(self):
        """Bật bot (idempotent). -> True nếu đang chạy sau lệnh này."""
        if self.is_running():
            return True
        if not self.configured():
            self._last_error = "thiếu token hoặc chat_id"
            self._log("[Telegram] Không bật được: thiếu token / chat id.")
            return False
        self._stop.clear()
        self._last_error = ""
        self._primed = False
        self._started_at = time.time()
        self._thread = threading.Thread(target=self._loop, name="tg-password-bot", daemon=True)
        self._thread.start()
        self._log(f"[Telegram] Đã bật bot (chat {self.chat_id}) — gõ /help trên Telegram.")
        return True

    def stop(self, wait=False):
        """Tắt bot. Không join mặc định vì getUpdates có thể đang chờ ~25s."""
        was = self.is_running()
        self._stop.set()
        if wait and self._thread is not None:
            try:
                self._thread.join(timeout=3)
            except Exception:
                pass
        self._thread = None
        if was:
            self._log("[Telegram] Đã tắt bot.")

    def _loop(self):
        while not self._stop.is_set():
            try:
                if not self._primed:
                    self._prime_offset()
                self._poll_once()
            except Exception as e:  # mạng lỗi, JSON lỗi... -> nghỉ rồi thử lại
                self._last_error = str(e)[:200]
                self._log(f"[Telegram] Lỗi vòng chạy (thử lại sau): {self._last_error}")
                if self._stop.wait(5):
                    break

    def _prime_offset(self):
        """Bỏ qua backlog lệnh cũ sau khi app khởi động lại (offset=-1 lấy update cuối)."""
        self._primed = True
        data = self._call("GET", "getUpdates", params={"offset": -1, "limit": 1, "timeout": 0}, timeout=15)
        try:
            results = data.get("result") or []
            if results:
                self._offset = int(results[-1].get("update_id", 0)) + 1
        except Exception:
            pass

    def _call(self, method, api_method, params=None, payload=None, timeout=20):
        url = f"{self.api_base}/bot{self.token}/{api_method}"
        return self.http(method, url, params=params, json=payload, timeout=timeout) or {}

    def _poll_once(self):
        data = self._call(
            "GET", "getUpdates",
            params={"offset": self._offset, "timeout": self.poll_timeout},
            timeout=self.poll_timeout + 20,
        )
        if not data.get("ok", True if "result" in data else False):
            desc = data.get("description") or "getUpdates thất bại"
            if desc != self._last_error:
                self._last_error = str(desc)[:200]
                self._log(f"[Telegram] getUpdates lỗi: {self._last_error}")
            if self._stop.wait(5):
                return
            return
        for upd in data.get("result") or []:
            if self._stop.is_set():
                return
            try:
                self._offset = int(upd.get("update_id", self._offset)) + 1
            except Exception:
                pass
            self._handle_update(upd)

    def _handle_update(self, upd):
        msg = upd.get("message") or upd.get("edited_message") or {}
        if not isinstance(msg, dict):
            return
        chat_raw = (msg.get("chat") or {}).get("id")
        if chat_raw is None:
            return
        if str(chat_raw).strip() != self.chat_id:
            self._log(f"[Telegram] Bỏ qua lệnh từ chat lạ: {chat_raw}")
            return
        text = msg.get("text") or ""
        if not text.strip().startswith("/"):
            return
        self._log(f"[Telegram] Nhận lệnh: {text.strip()[:80]}")
        reply = self.handle_text(text)
        if reply:
            self.send(reply)

    def send(self, text):
        """Gửi message về chat đã khoá. -> True/False."""
        try:
            data = self._call(
                "POST", "sendMessage",
                payload={"chat_id": self.chat_id, "text": str(text)[:4000],
                         "disable_web_page_preview": True},
                timeout=20,
            )
            ok = bool(data.get("ok"))
            if not ok:
                self._last_error = str(data.get("description") or "")[:200]
                self._log(f"[Telegram] Gửi lỗi: {self._last_error}")
            return ok
        except Exception as e:
            self._last_error = str(e)[:200]
            self._log(f"[Telegram] Gửi lỗi: {self._last_error}")
            return False

    # ------------------------------------------------------------- lệnh
    def handle_text(self, text, now=None):
        """Xử lý 1 câu lệnh, trả về text trả lời (rỗng = không trả lời)."""
        now = time.time() if now is None else float(now)
        raw = (text or "").strip()
        if not raw:
            return ""
        head, _, rest = raw.partition(" ")
        cmd = head.split("@")[0].strip().lower()
        rest = rest.strip()

        if cmd in ("/help", "/start", "/trogiup", "/huongdan"):
            return CMD_HELP
        if cmd in ("/status", "/trangthai", "/tt"):
            return self._cmd_status(now)
        if cmd in ("/set", "/doi", "/doimk", "/changepassword"):
            return self._cmd_set(rest, now)
        if cmd in ("/reset", "/quen", "/quenmk"):
            return self._cmd_reset(now)
        if cmd in ("/confirm", "/xacnhan"):
            return self._cmd_confirm(rest, now)
        if cmd in ("/cancel", "/huy"):
            if self._reset_code:
                self._clear_reset()
                return "Đã huỷ mã đang chờ. Không có thay đổi nào."
            return "Không có mã nào đang chờ."
        return "Lệnh không hợp lệ.\n\n" + CMD_HELP

    def _cmd_status(self, now):
        custom = _safe_vault("has_custom_password")
        if custom:
            pw = "đã đặt mật khẩu riêng"
        elif custom is False:
            pw = "vẫn dùng mật khẩu mặc định (nên đổi)"
        else:
            pw = "không đọc được cấu hình"
        lines = [self.status_text(), f"Cổng API key: {pw}"]
        if self._lock_until > now:
            lines.append(f"Tạm khoá do sai nhiều: còn {int(self._lock_until - now)}s")
        return "\n".join(lines)

    def _cmd_set(self, rest, now):
        blocked = self._blocked_reply(now)
        if blocked:
            return blocked
        parts = rest.split(None, 1)
        if len(parts) < 2:
            return "Cú pháp: /set MẬT_KHẨU_CŨ MẬT_KHẨU_MỚI   (không gõ dấu < >)"
        old, new = _clean_arg(parts[0]), _clean_arg(parts[1])
        if len(new) < MIN_PASSWORD_LEN:
            # sai cú pháp KHÔNG tính là dò mật khẩu
            return f"Mật khẩu mới phải từ {MIN_PASSWORD_LEN} ký tự. Không có thay đổi nào."
        ok = _safe_vault("check_password", old)
        if not ok:
            self._note_fail(now)
            left = ""
            if self._lock_until > now:
                left = f"\nĐã tạm khoá {LOCK_SECONDS // 60} phút vì sai quá {MAX_FAILS} lần."
            return "Mật khẩu cũ không đúng. Không có thay đổi nào." + left
        if not _safe_vault("set_password", new):
            return "Không ghi được mật khẩu mới (lỗi lưu cấu hình). Thử lại sau."
        self._note_ok()
        self._notify_changed()
        return ("Đã đổi mật khẩu cổng API key.\n"
                f"Mật khẩu cũ KHÔNG còn hiệu lực. ({len(new)} ký tự mới)")

    def _cmd_reset(self, now):
        blocked = self._blocked_reply(now)
        if blocked:
            return blocked
        code = f"{secrets.randbelow(1000000):06d}"
        self._reset_code = code
        self._reset_expires = now + RESET_TTL
        self._reset_tries = 0
        self._log("[Telegram] Đã sinh mã xác nhận /confirm (hiệu lực 5 phút).")
        return ("Mã xác nhận: {}\n"
                "Hiệu lực {} phút, dùng 1 lần.\n"
                "Đổi mật khẩu: /confirm {} MẬT_KHẨU_MỚI\n"
                "Huỷ mã: /cancel").format(code, RESET_TTL // 60, code)

    def _cmd_confirm(self, rest, now):
        blocked = self._blocked_reply(now)
        if blocked:
            return blocked
        parts = rest.split(None, 1)
        if len(parts) < 2:
            return "Cú pháp: /confirm MÃ_XÁC_NHẬN MẬT_KHẨU_MỚI   (không gõ dấu < >)"
        code, new = _clean_arg(parts[0]), _clean_arg(parts[1])
        if not self._reset_code:
            return "Chưa có mã nào. Gửi /reset trước."
        if now > self._reset_expires:
            self._clear_reset()
            return "Mã đã hết hạn. Gửi /reset để lấy mã mới."
        if len(new) < MIN_PASSWORD_LEN:
            return f"Mật khẩu mới phải từ {MIN_PASSWORD_LEN} ký tự. Không có thay đổi nào."
        if not secrets.compare_digest(str(code), str(self._reset_code)):
            self._reset_tries += 1
            if self._reset_tries >= RESET_MAX_TRIES:
                self._clear_reset()
                self._note_fail(now)
                return f"Sai mã {RESET_MAX_TRIES} lần — đã huỷ mã. Gửi /reset để lấy mã mới."
            left = RESET_MAX_TRIES - self._reset_tries
            return f"Mã không đúng. Còn {left} lần thử."
        self._clear_reset()
        if not _safe_vault("set_password", new):
            return "Không ghi được mật khẩu mới (lỗi lưu cấu hình). Thử lại sau."
        self._note_ok()
        self._notify_changed()
        return ("Đã đặt lại mật khẩu cổng API key bằng mã xác nhận.\n"
                f"Mật khẩu cũ (kể cả mặc định) KHÔNG còn hiệu lực. ({len(new)} ký tự mới)")

    # ------------------------------------------------------------- nội bộ
    def _clear_reset(self):
        self._reset_code = ""
        self._reset_expires = 0.0
        self._reset_tries = 0

    def _blocked_reply(self, now):
        if self._lock_until <= now:
            if self._lock_until:
                self._lock_until = 0.0
                self._fails = 0
            return ""
        left = max(1, int(self._lock_until - now))
        return f"Đang tạm khoá do sai quá {MAX_FAILS} lần. Thử lại sau {left}s."

    def _note_fail(self, now):
        self._fails += 1
        if self._fails >= MAX_FAILS:
            self._lock_until = now + LOCK_SECONDS
            self._fails = 0

    def _note_ok(self):
        self._fails = 0
        self._lock_until = 0.0

    def _notify_changed(self):
        if self.on_password_changed is None:
            return
        try:
            self.on_password_changed()
        except Exception:
            pass


def _fmt_dur_block(seconds):
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"
