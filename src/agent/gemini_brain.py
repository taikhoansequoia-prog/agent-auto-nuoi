import os
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


class GeminiBrain(BaseBrain):
    def __init__(self, api_key: str, model_name="gemini-flash-latest", endpoint=None):
        # v1.5.6: endpoint trống -> cổng chính của SDK; có endpoint -> ghi đè (proxy/gateway riêng).
        endpoint = (endpoint or "").strip()
        if endpoint:
            try:
                genai.configure(api_key=api_key, api_endpoint=endpoint)
                print(f"[*] Gemini dùng cổng tự đặt: {endpoint}")
            except TypeError:
                # SDK cũ không nhận api_endpoint -> quay về configure thường (không sập brain).
                genai.configure(api_key=api_key)
                print("[!] SDK Gemini không hỗ trợ api_endpoint - dùng cổng chính.")
        else:
            genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)

    def ask_text(self, prompt: str) -> str:
        """Gửi text prompt thuần túy, nhận về string."""
        try:
            response = self.model.generate_content(
                prompt, request_options={"timeout": _GEMINI_TIMEOUT_S})
            return response.text.strip() if response.text else ""
        except Exception as e:
            print(f"[-] Lỗi Gemini Brain (ask_text): {e}")
            return ""

    def analyze_screen(self, prompt: str, image_path: str) -> dict:
        try:
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