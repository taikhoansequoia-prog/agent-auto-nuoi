import sys
import os
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.browser.antidetect import AntidetectAPI
from src.browser.playwright_core import BrowserController
from src.agent.brain_manager import BrainManager

PROFILE_ID = "4bc996cf-331c-41c2-bba7-bad8db662136"

def test_run():
    api = AntidetectAPI()
    ws_url = api.open_profile(PROFILE_ID)
    
    if not ws_url:
        print("Không thể lấy được WebSocket URL. Dừng chương trình.")
        return

    controller = BrowserController(ws_url)
    
    try:
        if controller.connect():
            # Truy cập web cần thao tác (Ví dụ vào google để click nút đăng nhập)
            controller.goto_url("https://www.google.com")
            time.sleep(2) 
            
            # 1. Bơm JS vẽ khung đỏ và lấy danh sách Box ID kèm toạ độ
            controller.mark_elements()
            
            # 2. Chụp màn hình (Lúc này màn hình đã có sẵn các khung đỏ)
            img_path = controller.take_screenshot("test_screenshot_marked.png")
            
            # 3. Gửi ảnh cho Gemini kèm Prompt Set-of-Mark
            controller.remove_marks()
            brain = BrainManager.get_brain("openai")  # Hoặc "gemini", "local" tuỳ nhu cầu
            
            prompt = """
            Bạn là một Web Agent. Trong ảnh được cung cấp, các phần tử có thể tương tác 
            đã được đóng khung đỏ và đánh số. 
            Nhiệm vụ của bạn là tìm nút "Đăng nhập" (Sign in) và trả về ID của hộp đỏ đó.
            
            Trả về JSON có cấu trúc chính xác như sau:
            {"action": "click", "box_id": [Nhập số nguyên ở đây]}
            
            Nếu không tìm thấy, trả về: {"action": "none", "box_id": 0}
            """
            
            print("[*] Đang gửi ảnh đã đánh dấu cho AI...")
            result = brain.analyze_screen(prompt, img_path)
            print(f"[+] Quyết định của AI: {result}")

            
            # 4. Thực thi lệnh từ AI
            if result.get("action") == "click" and result.get("box_id"):
                box_id_number = result.get("box_id")
                
                # Gọi hàm click theo ID (Playwright sẽ tự tính toán mọi góc cuộn)
                controller.click_by_ai_id(box_id_number)
                time.sleep(3)
            
    except Exception as e:
        print(f"[-] Đã xảy ra lỗi: {e}")
        
    finally:
        print("[*] Đang dọn dẹp và đóng tài nguyên...")
        controller.close()
        api.close_profile(PROFILE_ID)

if __name__ == "__main__":
    test_run()