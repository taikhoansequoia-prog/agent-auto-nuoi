import google.generativeai as genai
import json
from .base_brain import BaseBrain

class GeminiBrain(BaseBrain):
    def __init__(self, api_key: str, model_name="gemini-1.5-flash"):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)

    def ask_text(self, prompt: str) -> str:
        """Gửi text prompt thuần túy, nhận về string."""
        try:
            response = self.model.generate_content(prompt)
            return response.text.strip() if response.text else ""
        except Exception as e:
            print(f"[-] Lỗi Gemini Brain (ask_text): {e}")
            return ""

    def analyze_screen(self, prompt: str, image_path: str) -> dict:
        try:
            img_file = genai.upload_file(path=image_path)
            response = self.model.generate_content(
                [prompt, img_file],
                generation_config=genai.GenerationConfig(response_mime_type="application/json")
            )
            return json.loads(response.text)
        except Exception as e:
            print(f"[-] Lỗi Gemini Brain: {e}")
            return {"action": "error", "message": str(e)}