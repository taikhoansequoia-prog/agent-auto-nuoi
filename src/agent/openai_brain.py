import os
import json
import base64
from openai import OpenAI

class OpenAIBrain:
    def __init__(self, api_key=None, model_name="gpt-4o"):
        """
        Khởi tạo OpenAI Brain với API Key và Model mặc định (gpt-4o tối ưu cho vision và text).
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key)
        self.model_name = model_name

    def analyze_text(self, prompt):
        """
        Dùng cho các tác vụ thuần văn bản (Ví dụ: AI suy nghĩ chủ đề, sinh từ khóa...).
        Trả về dictionary (JSON).
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                response_format={"type": "json_object"}, # Ép OpenAI trả về cấu trúc JSON
                messages=[
                    {
                        "role": "system", 
                        "content": "You are a helpful assistant that always outputs valid JSON."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                temperature=0.7
            )
            
            content = response.choices[0].message.content
            return json.loads(content)
            
        except Exception as e:
            print(f"[-] Lỗi OpenAI Brain (analyze_text): {e}")
            return {"action": "error", "message": str(e)}

    def analyze_screen(self, prompt, image_path=None):
        """
        Xử lý màn hình (Vision) hoặc fallback sang Text nếu không có ảnh truyền vào.
        Khắc phục hoàn toàn lỗi expected str, bytes or os.PathLike object, not NoneType.
        """
        try:
            # TRƯỜNG HỢP 1: Không có ảnh -> Chuyển sang xử lý thuần text an toàn
            if not image_path:
                return self.analyze_text(prompt)

            # TRƯỜNG HỢP 2: Có ảnh -> Đọc file ảnh và gửi kèm OpenAI Vision
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"Không tìm thấy file ảnh tại đường dẫn: {image_path}")

            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')

            response = self.client.chat.completions.create(
                model=self.model_name,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text", 
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=500
            )

            content = response.choices[0].message.content
            return json.loads(content)

        except Exception as e:
            print(f"[-] Lỗi OpenAI Brain (analyze_screen): {e}")
            return {"action": "error", "message": str(e)}