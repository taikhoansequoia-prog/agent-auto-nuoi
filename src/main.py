import sys
import os
import time
import random
import json

# Đảm bảo Python nhận diện được thư mục src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from src.browser.bitbrowser_api import BitBrowserAPI
from src.browser.playwright_core import BrowserController
from src.agent.brain_manager import BrainManager
from src.database.db_handler import DatabaseHandler
from src.workflow.warmup import WarmupWorkflow

import os
import random

def get_daily_theme_from_file():
    """Đọc file keywords.txt nằm ngay cùng thư mục với file main.py hiện tại"""
    print("  [*] Đang tìm file từ khóa ngay cạnh main.py...")
    
    fallback_theme = {
        "google_query": "tin tức kinh tế vĩ mô", 
        "youtube_query": "global macro economics"
    }
    
    # Lấy chính xác thư mục chứa file chứa đoạn code này (tức là file main.py)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Ghép thành đường dẫn tuyệt đối: Thư mục chứa main.py + keywords.txt
    target_file = os.path.join(current_dir, "keywords.txt")
    
    # Nếu không thấy bản chữ thường, thử tìm xem lỡ có bản viết hoa không để tự động linh động
    if not os.path.exists(target_file):
        alt_file = os.path.join(current_dir, "Keywords.txt")
        if os.path.exists(alt_file):
            target_file = alt_file
        else:
            print(f"  [-] Không tìm thấy file 'keywords.txt' tại đường dẫn: {target_file}")
            print(f"  [-] Sẽ dùng chủ đề dự phòng.")
            return fallback_theme
            
    try:
        # Dùng utf-8-sig để chống lỗi BOM của Windows Notepad
        with open(target_file, 'r', encoding='utf-8-sig') as f:
            lines = [line.strip() for line in f if line.strip()]
            
        if not lines:
            print(f"  [-] File {os.path.basename(target_file)} đang trống. Sẽ dùng chủ đề dự phòng.")
            return fallback_theme
            
        chosen_line = random.choice(lines)
        
        if "|" in chosen_line:
            google_q, youtube_q = chosen_line.split("|", 1)
            theme = {
                "google_query": google_q.strip(),
                "youtube_query": youtube_q.strip()
            }
        else:
            theme = {
                "google_query": chosen_line.strip(),
                "youtube_query": chosen_line.strip()
            }
            
        print(f"  [+] Đã chốt chủ đề từ file: Google [{theme['google_query']}] | YouTube [{theme['youtube_query']}]")
        return theme
        
    except Exception as e:
        print(f"  [-] Lỗi đọc file từ khóa: {e}. Sẽ dùng chủ đề dự phòng.")
        return fallback_theme
    
    
def main():
    # Điền các ID Profile (Browser ID) bạn lấy từ phần mềm BitBrowser vào đây
    PROFILES = [
        "34ac50372ec9411dadaca8ed8bb70905",
    ]

    db = DatabaseHandler()
    api = BitBrowserAPI(port=54345) # Khởi tạo API kết nối với BitBrowser
    
    print("🚀 BẮT ĐẦU HỆ THỐNG AGENT (BITBROWSER + ORGANIC TRAFFIC) 🚀")

    for profile_id in PROFILES:
        print(f"\n{'='*60}")
        print(f"[*] Bắt đầu xử lý Profile: {profile_id}")
        
        # 1. Kiểm tra giới hạn Sub hôm nay từ SQLite
        needs_sub = db.can_subscribe_today(profile_id)
        
        # 2. Gọi BitBrowser mở Profile và lấy URL WebSocket
        ws_url = api.open_profile(profile_id)
        if not ws_url:
            print(f"[-] Bỏ qua Profile {profile_id} do lỗi mở trình duyệt.")
            continue

        controller = BrowserController(ws_url)
        
        try:
            # 3. Kết nối Playwright vào lõi trình duyệt
            if controller.connect():
                context = controller.browser.contexts[0]
                
                # 4. AI lên kế hoạch nội dung cho phiên chạy
                session_theme = get_daily_theme_from_file()
                
                print("\n[*] CHUYỂN SANG GIAI ĐOẠN WARM-UP & TỰ ĐỘNG XEM/SUB LIÊN HOÀN...")
                
                # 5. Khởi tạo Kịch bản
                warmup = WarmupWorkflow(
                    context=context, 
                    db_handler=db, 
                    profile_id=profile_id, 
                    needs_sub=needs_sub,
                    session_theme=session_theme
                )
                
                # Chạy ngẫu nhiên từ 5 đến 8 hành động (Báo chí, Google, Chuỗi YouTube...)
                total_actions = random.randint(3, 5)
                warmup.run_random_session(total_actions=total_actions)
                
        except Exception as e:
            print(f"[-] Đã xảy ra lỗi hệ thống với Profile {profile_id}: {e}")
            
        finally:
            print(f"\n[*] Đang dọn dẹp tài nguyên Playwright...")
            controller.close()
            
            # 6. Đóng BitBrowser để giải phóng RAM
            api.close_profile(profile_id)
            print("[*] Nghỉ 5s trước khi chạy Profile tiếp theo...")
            time.sleep(5) 

    print("\n🎉 ĐÃ HOÀN THÀNH TOÀN BỘ DANH SÁCH PROFILE 🎉")

if __name__ == "__main__":
    main()