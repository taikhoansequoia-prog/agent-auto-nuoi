import requests
import time

class BitBrowserAPI:
    def __init__(self, port=54345):
        """Khởi tạo kết nối với Local API của BitBrowser"""
        self.base_url = f"http://127.0.0.1:54345"

    def open_profile(self, profile_id):
        """Mở profile và lấy địa chỉ WebSocket (ws://) cho Playwright"""
        url = f"{self.base_url}/browser/open"
        headers = {'Content-Type': 'application/json'}
        # BitBrowser thường dùng tham số 'id' để xác định profile
        payload = {"id": profile_id}
        
        try:
            print(f"[*] Đang yêu cầu BitBrowser mở Profile ID: {profile_id}...")
            response = requests.post(url, json=payload, headers=headers)
            result = response.json()
            
            # Kiểm tra trạng thái trả về (BitBrowser thường trả về success=True)
            if result.get("success"):
                # Bóc tách địa chỉ WebSocket từ data trả về
                ws_url = result.get("data", {}).get("ws")
                if ws_url:
                    print(f"  [+] Mở thành công! WebSocket URL: {ws_url}")
                    return ws_url
            
            print(f"  [-] Lỗi từ BitBrowser API: {result.get('msg', result)}")
            return None
            
        except Exception as e:
            print(f"  [-] Không thể kết nối tới BitBrowser (Vui lòng kiểm tra xem app đã bật chưa). Lỗi: {e}")
            return None

    def close_profile(self, profile_id):
        """Đóng profile sau khi chạy xong"""
        url = f"{self.base_url}/browser/close"
        headers = {'Content-Type': 'application/json'}
        payload = {"id": profile_id}
        
        try:
            print(f"[*] Đang đóng Profile ID: {profile_id} trên BitBrowser...")
            response = requests.post(url, json=payload, headers=headers)
            if response.json().get("success"):
                print("  [+] Đã đóng profile thành công.")
                return True
            return False
        except Exception as e:
            print(f"  [-] Lỗi khi đóng profile: {e}")
            return False