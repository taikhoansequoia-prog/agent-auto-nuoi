import requests

class AntidetectAPI:
    def __init__(self, base_url="http://localhost:9495"):
        """
        Khởi tạo kết nối với Local API của GPM Login.
        Lưu ý: Thay đổi port trong base_url nếu GPM Login của bạn dùng port khác
        (bạn có thể đang dùng port của file cũ, nếu code cũ chạy được thì cứ dùng URL cũ).
        """
        # Nếu URL cũ bạn dùng đang hoạt động trả về kết quả, hãy sửa lại base_url cho khớp.
        self.base_url = base_url

    def open_profile(self, profile_id):
        """Mở profile và lấy địa chỉ WebSocket (ws://) cho Playwright"""
        url = f"{self.base_url}/api/v1/profiles/start/{profile_id}"
        
        try:
            print(f"[*] Đang yêu cầu API mở Profile ID: {profile_id}...")
            
            response = requests.get(url)
            
            if response.status_code != 200:
                print(f"  [-] API thất bại với mã lỗi HTTP {response.status_code}.")
                print(f"  [-] Nội dung server trả về (Raw Text): {response.text}")
                return None
                
            try:
                result = response.json()
            except Exception as json_err:
                print(f"  [-] Lỗi không thể đọc JSON: {json_err}")
                return None
            
            # Cập nhật chính xác key 'websocket_debugging_url' dựa trên log của GPM v5.0.8
            if result.get("success") == True or result.get("status") == True:
                data_block = result.get("data", {})
                
                # Ưu tiên bắt key websocket_debugging_url trước
                ws_url = data_block.get("websocket_debugging_url") or data_block.get("ws") or data_block.get("websocket")
                
                if ws_url:
                    print(f"  [+] Mở thành công! WebSocket URL: {ws_url}")
                    return ws_url
            
            print(f"  [-] Lỗi từ nội dung API (Không tìm thấy link ws): {result}")
            return None
            
        except requests.exceptions.RequestException as e:
            print(f"  [-] Lỗi kết nối mạng tới API: {e}")
            return None

    def get_profile_name(self, profile_id):
        """Gọi API lấy chi tiết profile để trích xuất tên hiển thị cho UI"""
        url = f"{self.base_url}/api/v1/profiles/{profile_id}"
        try:
            response = requests.get(url, timeout=3)
            if response.status_code == 200:
                data = response.json()
                if data.get("success") and "data" in data:
                    return data["data"].get("name", profile_id[:8])
        except Exception:
            pass
        return profile_id[:8] # Fallback lấy 8 ký tự ID nếu API không phản hồi

    def close_profile(self, profile_id):
        """
        Đóng profile sau khi đã hoàn thành tác vụ
        """
        url = f"{self.base_url}/api/v1/profiles/stop/{profile_id}"
        
        try:
            response = requests.get(url).json()
            if response.get("success") == True:
                print(f"[+] Đã đóng Profile {profile_id}.")
                return True
            return False
        except Exception as e:
            print(f"[-] Lỗi khi đóng Profile {profile_id}: {e}")
            return False