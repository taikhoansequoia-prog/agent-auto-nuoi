import os
import json
import base64
from openai import OpenAI
from .base_brain import BaseBrain


class GenericLLMBrain(BaseBrain):
    """Bộ não LLM tổng quát, tương thích mọi API theo chuẩn OpenAI (OpenAI, Qwen, Ollama...)."""

    def __init__(self, api_key=None, model_name="gpt-4o", base_url=None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        kwargs = {"api_key": self.api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)
        self.model_name = model_name

    def ask_text(self, prompt: str) -> str:
        """Gửi text prompt thuần túy, nhận về string. Dùng cho keyword generation."""
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "Bạn là trợ lý tạo từ khóa. Chỉ trả về duy nhất từ khóa, không giải thích, không dấu ngoặc."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                timeout=10
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[-] Lỗi GenericLLMBrain (ask_text): {e}")
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