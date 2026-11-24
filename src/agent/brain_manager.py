import os

from dotenv import load_dotenv

# Nạp biến môi trường từ file .env ở thư mục gốc dự án
load_dotenv()

# v1.7.1: gom NHIỀU key của cùng một dịch vụ để xoay vòng (GEMINI_API_KEY=k1,k2 hoặc
# GEMINI_API_KEY_2/_3...). Bọc try vì test cũ stub sys.modules và CLI có thể chạy ngoài
# package `src` -> thiếu thì rơi về đúng 1 key như trước, không gãy gì.
try:
    from src.api_vault import get_keys as _get_keys
except Exception:
    _get_keys = None


def _collect_keys(name):
    """-> danh sách key của một dịch vụ (ít nhất rỗng). Fallback: 1 key từ os.getenv."""
    keys = []
    if _get_keys is not None:
        try:
            keys = list(_get_keys(name) or [])
        except Exception:
            keys = []
    if not keys:
        one = os.getenv(name)
        if one:
            keys = [one.strip()]
    return [k for k in keys if k]


# v1.7.2: brain Claude qua cổng tương thích OpenAI (gateway của user). Key có thể mang tên
# chuẩn CLAUDE_API_KEY hoặc tên user tự đặt CLAUDE_LAU — thử lần lượt. Cổng BẮT BUỘC khai
# trong biến đi kèm <TEN_KEY>_ENDPOINT (ô "Endpoint" trong dialog QUẢN LÝ API KEY).
CLAUDE_KEY_NAMES = ("CLAUDE_API_KEY", "CLAUDE_LAU")
CLAUDE_MODELS = {
    "claude-sonnet": "claude-sonnet-5-5",
    "claude-haiku": "claude-haiku-5-5",
}


# v1.7.6: brain cổng tự đặt -> "custom:<TEN_KEY>"
CUSTOM_PREFIX = "custom:"


def _claude_credentials():
    """-> (tên biến, danh sách key, endpoint). Không có key -> (None, [], '')."""
    for name in CLAUDE_KEY_NAMES:
        keys = _collect_keys(name)
        if keys:
            return name, keys, (os.getenv(f"{name}_ENDPOINT") or "").strip()
    return None, [], ""


class BrainManager:
    @staticmethod
    def get_brain(brain_type="gemini"):
        """
        Nhập tên brain muốn dùng: 'gemini', 'local', 'openai', 'qwen-max', 'qwen-flash',
        'claude-sonnet', 'claude-haiku'.
        Import module brain một cách lười biếng (lazy) để tránh ép cài tất cả SDK.
        """
        if brain_type in ("claude-account", "chatgpt-account"):
            # v1.12.0: AI qua TÀI KHOẢN ĐĂNG NHẬP (Claude Code / Codex) — không API key. Chưa cài/chưa đăng nhập -> ném lỗi.
            from .account_brain import get_account_brain
            return get_account_brain(brain_type)

        if brain_type == "gemini":
            from .gemini_brain import GeminiBrain
            # v1.7.1: nhiều key -> xoay vòng; 1 key -> y hệt trước đây.
            keys = _collect_keys("GEMINI_API_KEY")
            if not keys:
                raise ValueError(
                    "Thiếu GEMINI_API_KEY. Hãy khai báo trong file .env (xem .env.example)."
                )
            # v1.5.6: GEMINI_API_KEY_ENDPOINT trống -> cổng chính; có -> cổng tự đặt.
            return GeminiBrain(api_key=keys[0], api_keys=keys,
                               endpoint=os.getenv("GEMINI_API_KEY_ENDPOINT") or None)

        elif brain_type == "local":
            from .local_brain import LocalBrain
            return LocalBrain(model_name="llava")

        elif brain_type == "openai":
            from .openai_brain import OpenAIBrain
            # v1.7.2: nhiều key -> xoay vòng; 1 key -> y hệt trước đây.
            keys = _collect_keys("OPENAI_API_KEY")
            if not keys:
                raise ValueError(
                    "Thiếu OPENAI_API_KEY. Hãy khai báo trong file .env (xem .env.example)."
                )
            # v1.5.6: OPENAI_API_KEY_ENDPOINT trống -> cổng chính của SDK; có -> ghi đè.
            return OpenAIBrain(api_key=keys[0], api_keys=keys, model_name="gpt-5-mini",
                               base_url=os.getenv("OPENAI_API_KEY_ENDPOINT") or None)

        elif brain_type in CLAUDE_MODELS:
            # v1.7.2: Claude qua cổng tương thích OpenAI. Nhiều key -> xoay vòng như Gemini.
            from .openai_brain import GenericLLMBrain
            name, keys, endpoint = _claude_credentials()
            if not keys:
                raise ValueError(
                    "Thiếu key Claude. Mở nút QUẢN LÝ API KEY rồi thêm CLAUDE_API_KEY "
                    "(hoặc CLAUDE_LAU) kèm ô Endpoint của cổng bạn dùng."
                )
            if not endpoint:
                raise ValueError(
                    f"Key {name} chưa có endpoint. Mở QUẢN LÝ API KEY -> Sửa {name} -> "
                    f"điền ô 'Endpoint' (vd https://api.mwapi.dev/v1)."
                )
            return GenericLLMBrain(api_key=keys[0], api_keys=keys,
                                   model_name=CLAUDE_MODELS[brain_type], base_url=endpoint)

        elif isinstance(brain_type, str) and brain_type.startswith(CUSTOM_PREFIX):
            # v1.7.6: MỌI key có Endpoint (cổng tương thích OpenAI: kiraai, mwapi,
            # openrouter...) dùng được làm brain. Model lấy từ <TEN>_MODEL.
            from .openai_brain import GenericLLMBrain
            name = brain_type[len(CUSTOM_PREFIX):].strip().upper()
            keys = _collect_keys(name)
            if not keys:
                raise ValueError(f"Thiếu key {name}. Mở QUẢN LÝ API KEY để thêm.")
            endpoint = (os.getenv(f"{name}_ENDPOINT") or "").strip()
            model = (os.getenv(f"{name}_MODEL") or "").strip()
            if not endpoint:
                raise ValueError(f"Key {name} chưa có endpoint. Mở QUẢN LÝ API KEY -> Sửa {name} "
                                 f"-> điền ô 'Endpoint'.")
            if not model:
                raise ValueError(f"Key {name} chưa có tên model. Mở QUẢN LÝ API KEY -> Sửa {name} "
                                 f"-> điền ô 'Model' (vd deepseek-v4.1-flash).")
            return GenericLLMBrain(api_key=keys[0], api_keys=keys,
                                   model_name=model, base_url=endpoint)

        elif brain_type in ("qwen-max", "qwen-flash"):
            from .openai_brain import GenericLLMBrain
            keys = _collect_keys("QWEN_API_KEY") or _collect_keys("DASHSCOPE_API_KEY")
            if not keys:
                raise ValueError(
                    "Thiếu QWEN_API_KEY. Hãy khai báo trong file .env."
                )
            api_key = keys[0]
            model = "qwen-max" if brain_type == "qwen-max" else "qwen-plus"
            # v1.5.6: QWEN_API_KEY_ENDPOINT trống -> cổng DashScope chính; có -> ghi đè.
            return GenericLLMBrain(
                api_key=api_key,
                api_keys=keys,
                model_name=model,
                base_url=os.getenv("QWEN_API_KEY_ENDPOINT") or "https://dashscope.aliyuncs.com/compatible-mode/v1"
            )

        else:
            raise ValueError(f"Không hỗ trợ bộ não: {brain_type}")
