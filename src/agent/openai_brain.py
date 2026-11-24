import os
import json
import base64
import threading
from openai import OpenAI
from .base_brain import BaseBrain

# v1.7.2: xoay vòng nhiều key (giống gemini_brain). Client của SDK OpenAI là per-instance
# nên không cần khoá lúc gọi, chỉ khoá bộ đếm + lúc dựng client mới.
_rr_lock = threading.Lock()
_rr_index = 0

# Lỗi "đổi key may ra khỏi" (hết credit/quota/key sai). Timeout & lỗi mạng KHÔNG nằm đây.
_ROTATE_ON = ("429", "quota", "exhaust", "rate limit", "ratelimit", "insufficient",
              "credit", "permission", "api key", "api_key", "invalid_api_key",
              "unauthorized", "authentication")


def _should_rotate(err_text):
    low = str(err_text or "").lower()
    return any(sig in low for sig in _ROTATE_ON)


class GenericLLMBrain(BaseBrain):
    """Bộ não LLM tổng quát, tương thích mọi API theo chuẩn OpenAI (OpenAI, Qwen, Claude gateway...)."""

    def __init__(self, api_key=None, model_name="gpt-4o", base_url=None, api_keys=None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url
        # v1.7.2: danh sách key để xoay vòng. Chỉ dựng client cho key ĐẦU ngay lúc này,
        # các key sau dựng lười (lần đầu dùng tới) -> giữ nguyên hành vi 1-key cũ.
        self._keys = [k for k in (list(api_keys) if api_keys else [self.api_key]) if k]
        if not self._keys:
            self._keys = [self.api_key]
        self.client = self._make_client(self._keys[0])
        self._clients = {0: self.client}
        self.model_name = model_name

    # ------------------------------------------------------------------ nội bộ
    def _make_client(self, key):
        kwargs = {"api_key": key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return OpenAI(**kwargs)

    def _client_for(self, idx):
        with _rr_lock:
            cli = self._clients.get(idx)
            if cli is None:
                cli = self._make_client(self._keys[idx])
                self._clients[idx] = cli
        return cli

    def _next_key_index(self):
        global _rr_index
        with _rr_lock:
            idx = _rr_index % len(self._keys)
            _rr_index = (_rr_index + 1) % max(1, len(self._keys))
        return idx

    # v1.7.3: lý do THẬT của lượt gọi hỏng gần nhất (403 hết số dư / 429 hết credit /
    # timeout...). ask_text nuốt lỗi rồi trả "" nên caller không biết vì sao -> UI chỉ nói
    # "bù mẫu offline". Caller nào cần nêu lý do thì đọc thuộc tính này.
    last_error = ""

    def _ask_raw(self, client, prompt, timeout=None):
        """-> (text, error_text). Không in log (caller quyết định).
        v1.8.9: timeout=None -> 10s như cũ; lượt hỏi dài (kế hoạch phiên) truyền số lớn hơn."""
        try:
            response = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "Bạn là trợ lý tạo từ khóa. Chỉ trả về duy nhất từ khóa, không giải thích, không dấu ngoặc."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                timeout=timeout or 10
            )
            self.last_error = ""
            return response.choices[0].message.content.strip(), ""
        except Exception as e:
            self.last_error = str(e)
            return "", str(e)

    # ------------------------------------------------------------------ API
    def ask_text(self, prompt: str, timeout=None) -> str:
        """Gửi text prompt thuần túy, nhận về string. Dùng cho keyword generation.
        v1.8.9: `timeout` (giây) tùy chọn cho lượt hỏi dài; mặc định 10s như cũ.

        1 key -> hành vi y hệt trước đây. Nhiều key -> xoay vòng từng lượt gọi, gặp lỗi
        hết credit/quota thì thử key kế (tối đa 3 lượt); lỗi timeout thì bỏ ngay.
        """
        if len(self._keys) <= 1:
            text, err = self._ask_raw(self.client, prompt, timeout)
            if err:
                print(f"[-] Lỗi GenericLLMBrain (ask_text): {err}")
            return text

        tries = min(len(self._keys), 3)
        idx = self._next_key_index()
        last = ""
        for attempt in range(tries):
            print(f"[*] LLM: dùng key #{idx + 1}/{len(self._keys)}.")
            text, err = self._ask_raw(self._client_for(idx), prompt, timeout)
            if text:
                return text
            last = err
            if not _should_rotate(err):
                break
            idx = (idx + 1) % len(self._keys)
            if attempt + 1 < tries:
                print(f"[*] LLM: key hết credit/quota -> xoay sang key #{idx + 1}.")
        if last:
            print(f"[-] Lỗi GenericLLMBrain (ask_text): {last}")
        return ""

    def ask_chat(self, system: str, user: str, timeout=60, temperature=0.2) -> str:
        """v1.9.1: hỏi đáp với LỜI DẶN HỆ THỐNG RIÊNG (ask_text ghim vai 'trợ lý tạo từ khóa, chỉ trả về
        từ khóa' nên không dùng cho hỏi đáp được). Không in gì; lỗi nằm ở self.last_error.
        Nhiều key -> xoay vòng + thử key kế khi hết credit/quota, giống ask_text."""
        tries = min(len(self._keys), 3) if len(self._keys) > 1 else 1
        idx = self._next_key_index() if len(self._keys) > 1 else 0
        for _attempt in range(tries):
            try:
                response = self._client_for(idx).chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    temperature=temperature,
                    timeout=timeout or 60,
                )
                self.last_error = ""
                return (response.choices[0].message.content or "").strip()
            except Exception as e:
                self.last_error = str(e)
                if not _should_rotate(e):
                    break
                idx = (idx + 1) % len(self._keys)
        return ""

    def analyze_text(self, prompt):
        """Dùng cho các tác vụ thuần văn bản cần trả về JSON dict."""
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that always outputs valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                timeout=10
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            print(f"[-] Lỗi GenericLLMBrain (analyze_text): {e}")
            return {"action": "error", "message": str(e)}

    def analyze_screen(self, prompt, image_path=None):
        """Xử lý màn hình (Vision) hoặc fallback sang Text nếu không có ảnh."""
        try:
            if not image_path:
                return self.analyze_text(prompt)

            if not os.path.exists(image_path):
                raise FileNotFoundError(f"Không tìm thấy file ảnh: {image_path}")

            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')

            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                        ]
                    }
                ],
                max_tokens=500,
                timeout=10
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            print(f"[-] Lỗi GenericLLMBrain (analyze_screen): {e}")
            return {"action": "error", "message": str(e)}


# Alias giữ tương thích ngược cho code cũ import OpenAIBrain
OpenAIBrain = GenericLLMBrain