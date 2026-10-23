import os

from dotenv import load_dotenv

# Nạp biến môi trường từ file .env ở thư mục gốc dự án
load_dotenv()


class BrainManager:
    @staticmethod
    def get_brain(brain_type="gemini"):
        """
        Nhập tên brain muốn dùng: 'gemini', 'local', 'openai', 'qwen-max', 'qwen-flash'
        Import module brain một cách lười biếng (lazy) để tránh ép cài tất cả SDK.
        """
        if brain_type == "gemini":
            from .gemini_brain import GeminiBrain
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError(
                    "Thiếu GEMINI_API_KEY. Hãy khai báo trong file .env (xem .env.example)."
                )
            # v1.5.6: GEMINI_API_KEY_ENDPOINT trống -> cổng chính; có -> cổng tự đặt.
            return GeminiBrain(api_key=api_key, endpoint=os.getenv("GEMINI_API_KEY_ENDPOINT") or None)

        elif brain_type == "local":
            from .local_brain import LocalBrain
            return LocalBrain(model_name="llava")

        elif brain_type == "openai":
            from .openai_brain import OpenAIBrain
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError(
                    "Thiếu OPENAI_API_KEY. Hãy khai báo trong file .env (xem .env.example)."
                )
            # v1.5.6: OPENAI_API_KEY_ENDPOINT trống -> cổng chính của SDK; có -> ghi đè.
            return OpenAIBrain(api_key=api_key, model_name="gpt-5-mini",
                               base_url=os.getenv("OPENAI_API_KEY_ENDPOINT") or None)

        elif brain_type in ("qwen-max", "qwen-flash"):
            from .openai_brain import GenericLLMBrain
            api_key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
            if not api_key:
                raise ValueError(
                    "Thiếu QWEN_API_KEY. Hãy khai báo trong file .env."
                )
            model = "qwen-max" if brain_type == "qwen-max" else "qwen-plus"
            # v1.5.6: QWEN_API_KEY_ENDPOINT trống -> cổng DashScope chính; có -> ghi đè.
            return GenericLLMBrain(
                api_key=api_key,
                model_name=model,
                base_url=os.getenv("QWEN_API_KEY_ENDPOINT") or "https://dashscope.aliyuncs.com/compatible-mode/v1"
            )

        else:
            raise ValueError(f"Không hỗ trợ bộ não: {brain_type}")
