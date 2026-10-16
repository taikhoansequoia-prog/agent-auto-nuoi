import requests
import json
from .base_brain import BaseBrain

class LocalBrain(BaseBrain):
    def __init__(self, model_name="llava", url="http://localhost:11434/api/generate"):
        self.model_name = model_name
        self.url = url

    def ask_text(self, prompt: str) -> str:
        """Gửi text prompt thuần túy tới Ollama, nhận về string."""
        try:
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False
            }
            response = requests.post(self.url, json=payload, timeout=30).json()
            return response.get("response", "").strip()
        except Exception as e:
            print(f"[-] Lỗi Local Brain (ask_text): {e}")
            return ""

    def analyze_screen(self, prompt: str, image_path: str) -> dict:
        try:
            # Chuyển ảnh sang dạng Base64
            b64_img = self.encode_image(image_path)
            
            payload = {
                "model": self.model_name,
                "prompt": prompt + "\nTrích xuất dưới dạng JSON hợp lệ, không kèm giải thích.",
                "images": [b64_img],
                "stream": False,
                "format": "json" # Ép Ollama trả về JSON
            }
            
            response = requests.post(self.url, json=payload).json()
            return json.loads(response.get("response", "{}"))
            
        except Exception as e:
            print(f"[-] Lỗi Local Brain: {e}")
            return {"action": "error", "message": str(e)}