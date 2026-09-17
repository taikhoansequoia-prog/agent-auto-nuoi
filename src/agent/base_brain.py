from abc import ABC, abstractmethod
import base64

class BaseBrain(ABC):
    @abstractmethod
    def analyze_screen(self, prompt: str, image_path: str) -> dict:
        """
        Hàm này bắt buộc các bộ não con phải viết code thực thi.
        Luôn trả về một Dictionary dạng: {"action": "click", "target": "..."}
        """
        pass
    
    # Hàm tiện ích dùng chung: Chuyển ảnh thành base64 để gửi qua API
    def encode_image(self, image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')