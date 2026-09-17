from .gemini_brain import GeminiBrain
from .local_brain import LocalBrain
from .openai_brain import OpenAIBrain
import os

from dotenv import load_dotenv

# Nạp biến môi trường từ file .env ở thư mục gốc dự án
load_dotenv()


class BrainManager:
    @staticmethod
    def get_brain(brain_type="gemini"):
        """
        Nhập tên brain muốn dùng: 'gemini', 'local', 'openai', 'claude'
        """
        if brain_type == "gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError(
                    "Thiếu GEMINI_API_KEY. Hãy khai báo trong file .env (xem .env.example)."
                )
            return GeminiBrain(api_key=api_key)

        elif brain_type == "local":
            return LocalBrain(model_name="llava")

        elif brain_type == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError(
                    "Thiếu OPENAI_API_KEY. Hãy khai báo trong file .env (xem .env.example)."
                )
            return OpenAIBrain(api_key=api_key, model_name="gpt-5-mini")
        else:
            raise ValueError(f"Không hỗ trợ bộ não: {brain_type}")
