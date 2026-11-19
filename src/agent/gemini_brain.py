import os
import threading
import google.generativeai as genai
import json
from .base_brain import BaseBrain

# v1.6.8: gói google.generativeai đã end-of-life; generate_content KHÔNG có timeout mặc
# định nên có thể treo 80s+ / vô hạn khi mạng kém -> UI "Sinh chủ đề" đứng hình. Ép deadline
# per-call để fail-fast (giống OpenAI/Qwen có timeout=10). Chỉnh qua env GEMINI_TIMEOUT nếu cần.
try:
    _GEMINI_TIMEOUT_S = int(os.getenv("GEMINI_TIMEOUT", "15"))
except (TypeError, ValueError):
    _GEMINI_TIMEOUT_S = 15

# v1.7.3 — TÊN MODEL. Google gỡ/đóng băng model rất thường xuyên và KHÔNG phải lúc nào
# cũng trả 404: đo thật 31/10/2026 với key của user — `GET /models` trả 200 trong 0.3s
# (key hoàn toàn hợp lệ) nhưng `gemini-flash-latest` (mặc định cũ) **TREO >120s** trên cả 3
# đường (REST thuần stdlib, SDK gRPC, SDK REST) và không bao giờ trả lời; `gemini-2.0-flash`
# / `gemini-2.5-flash` đã 404 "no longer available"; `gemini-3.8-flash` trả 503 quá tải.
# Hai cái CHẠY được: gemini-3-flash-preview (1.4s) và gemini-flash-lite-latest (6.8s).
# -> thử lần lượt rồi NHỚ cái chạy được, thay vì chết cứng vào 1 tên. Ghim tên khác qua
# env GEMINI_MODEL.
_GEMINI_MODELS = ("gemini-3-flash-preview", "gemini-flash-lite-latest", "gemini-flash-latest")

# v1.7.1 — XOAY VÒNG NHIỀU KEY.
# genai.configure() là TRẠNG THÁI TOÀN CỤC của SDK: nó đặt lại client_config và xoá
# cache client (_ClientManager.configure -> self.clients = {}). Nhưng GenerativeModel
# lại CACHE client của riêng nó (self._client) ở lần gọi đầu -> đổi key xong PHẢI
# dựng lại model, nếu không request vẫn đi bằng key cũ.
# Bộ đếm để ở module-level (không phải instance) để nhiều luồng warmup trải đều key.
_rr_lock = threading.Lock()
_rr_index = 0

# Lỗi "đổi key thì may ra khỏi" (hết quota / key sai / bị chặn). Timeout & lỗi mạng
# KHÔNG nằm ở đây: đổi key không chữa được chậm, chỉ đốt thêm 15s (bài học v1.6.8).
_ROTATE_ON = ("429", "quota", "exhaust", "rate limit", "ratelimit",
              "permission", "api key", "api_key", "invalid key", "unauthenticated")


# Model "biến mất / quá tải" — lỗi trả về NHANH nên cứ duyệt hết danh sách ứng viên.
_MODEL_GONE_ON = ("404", "503", "not available", "no longer", "high demand",
                  "overloaded", "unavailable")
# Model "treo" — chỉ biết sau khi ăn trọn timeout (đúng bệnh của gemini-flash-latest).
# CHỈ cho thử thêm ĐÚNG 1 model nữa, nếu không mỗi lượt hỏi tốn len(_GEMINI_MODELS) × 15s.
_MODEL_HANG_ON = ("deadline", "timeout", "timed out")
_MODEL_FALLBACK_ON = _MODEL_GONE_ON + _MODEL_HANG_ON


def _should_rotate(err_text):
    low = str(err_text or "").lower()
    return any(sig in low for sig in _ROTATE_ON)


class GeminiBrain(BaseBrain):
    def __init__(self, api_key: str, model_name="gemini-3-flash-preview", endpoint=None,
                 api_keys=None):
        # env GEMINI_MODEL thắng mọi thứ (để đổi nhanh khi Google lại gỡ model).
        model_name = (os.getenv("GEMINI_MODEL") or "").strip() or model_name
        # v1.5.6: endpoint trống -> cổng chính của SDK; có endpoint -> ghi đè (proxy/gateway riêng).
        endpoint = (endpoint or "").strip()
        # v1.7.1: api_keys = danh sách key để xoay vòng. Không truyền -> đúng 1 key như cũ.
        self.model_name = model_name
        self.endpoint = endpoint
        self._keys = [k for k in (list(api_keys) if api_keys else [api_key]) if k]
        if not self._keys:
            self._keys = [api_key]
        self._key_pos = 0  # chỉ số key đang dùng (để log cho người đọc)
        if endpoint:
            try:
                genai.configure(api_key=self._keys[0], api_endpoint=endpoint)
                print(f"[*] Gemini dùng cổng tự đặt: {endpoint}")
            except TypeError:
                # SDK cũ không nhận api_endpoint -> quay về configure thường (không sập brain).
                genai.configure(api_key=self._keys[0])
                print("[!] SDK Gemini không hỗ trợ api_endpoint - dùng cổng chính.")
        else:
            genai.configure(api_key=self._keys[0])
        self.model = genai.GenerativeModel(model_name)
        if len(self._keys) > 1:
            print(f"[*] Gemini: có {len(self._keys)} API key -> sẽ xoay vòng từng lượt gọi.")

    # ------------------------------------------------------------------ nội bộ
    def _next_key_index(self):
        """Chỉ số key kế tiếp theo vòng tròn (dùng chung cho mọi luồng)."""
        global _rr_index
        with _rr_lock:
            idx = _rr_index % len(self._keys)
            _rr_index = (_rr_index + 1) % max(1, len(self._keys))
        return idx

    def _use_key(self, idx):
        """Đổi SDK sang key thứ idx. Phải dựng lại model vì model cache client riêng."""
        key = self._keys[idx]
        if self.endpoint:
            try:
                genai.configure(api_key=key, api_endpoint=self.endpoint)
            except TypeError:
                genai.configure(api_key=key)
        else:
            genai.configure(api_key=key)
        self.model = genai.GenerativeModel(self.model_name)
        self._key_pos = idx

    # ------------------------------------------------------------------ API
    def ask_text(self, prompt: str) -> str:
        """Gửi text prompt thuần túy, nhận về string.

        1 key -> hành vi y hệt trước đây (không khoá, không configure lại).
        Nhiều key -> mỗi lượt gọi xoay sang key kế tiếp; gặp lỗi hết quota/key hỏng
        thì thử key sau (tối đa 3 lượt), lỗi timeout thì bỏ ngay.
        """
        if len(self._keys) <= 1:
            return self._ask_once(prompt)

        tries = min(len(self._keys), 3)
        idx = self._next_key_index()
        last = ""
        for attempt in range(tries):
            with _rr_lock:  # genai.configure là trạng thái toàn cục -> phải tuần tự hoá
                self._use_key(idx)
                print(f"[*] Gemini: dùng key #{idx + 1}/{len(self._keys)}.")
                text, err = self._ask_raw(prompt)
            if text:
                return text
            last = err
            if not _should_rotate(err):
                break
            idx = (idx + 1) % len(self._keys)
            if attempt + 1 < tries:
                print(f"[*] Gemini: key #{self._key_pos + 1} lỗi quota/khoá -> xoay sang key #{idx + 1}.")
        if last:
            print(f"[-] Lỗi Gemini Brain (ask_text): {last}")
        return ""

    # v1.7.3: lý do THẬT của lượt gọi hỏng gần nhất (504 deadline / quota...). Xem chú
    # thích cùng tên trong openai_brain.py.
    last_error = ""

    def _ask_raw(self, prompt):
        """-> (text, error_text). Không in log (caller quyết định in gì).

        v1.7.3: model chết (404/503) HOẶC treo tới hết timeout thì thử tên model kế tiếp
        trong _GEMINI_MODELS, và nhớ cái chạy được vào self.model_name cho các lượt sau.
        Lỗi quota/key thì KHÔNG đổi model (đổi cũng vô ích) — nhường cho cơ chế xoay key.
        """
        order = [self.model_name] + [m for m in _GEMINI_MODELS if m != self.model_name]
        err, tried, hang_retried = "", [], False
        for name in order:
            if name in tried:
                continue
            tried.append(name)
            try:
                if name != self.model_name:
                    self.model = genai.GenerativeModel(name)
                response = self.model.generate_content(
                    prompt, request_options={"timeout": _GEMINI_TIMEOUT_S})
                text = (response.text.strip() if response.text else "")
                if name != self.model_name:
                    print(f"[*] Gemini: model '{self.model_name}' không dùng được -> chuyển sang '{name}'.")
                    self.model_name = name
                self.last_error = ""
                return text, ""
            except Exception as e:
                err = str(e)
                self.last_error = err
                low = err.lower()
                if any(sig in low for sig in _MODEL_HANG_ON):
                    if hang_retried:   # đã trả giá 1 lần timeout rồi -> dừng, đừng đốt thêm
                        break
                    hang_retried = True
                    continue
                if not any(sig in low for sig in _MODEL_GONE_ON):
                    break              # quota/key sai -> đổi model vô ích
        return "", err

    def _ask_once(self, prompt):
        text, err = self._ask_raw(prompt)
        if err:
            print(f"[-] Lỗi Gemini Brain (ask_text): {err}")
        return text

    def analyze_screen(self, prompt: str, image_path: str) -> dict:
        try:
            if len(self._keys) > 1:
                # Lấy chỉ số TRƯỚC khi vào lock: _next_key_index cũng khoá _rr_lock,
                # mà threading.Lock KHÔNG reentrant -> lồng vào nhau là treo cứng.
                _idx = self._next_key_index()
                with _rr_lock:
                    self._use_key(_idx)
            img_file = genai.upload_file(path=image_path)
            response = self.model.generate_content(
                [prompt, img_file],
                generation_config=genai.GenerationConfig(response_mime_type="application/json"),
                request_options={"timeout": _GEMINI_TIMEOUT_S}
            )
            return json.loads(response.text)
        except Exception as e:
            print(f"[-] Lỗi Gemini Brain: {e}")
            return {"action": "error", "message": str(e)}
