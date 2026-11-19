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
        # v1.7.5: giữ lý do lỗi để UI báo đúng nguyên nhân (vd BrowserNotFound = thiếu nhân trình duyệt)
        self.last_error = ""

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
            msg = str(result.get("message") or "")
            if msg == "BrowserNotFound":
                ver = self._profile_browser_version(profile_id)
                self.last_error = (f"GPM chưa có nhân trình duyệt {ver or ''} cho profile này (BrowserNotFound). "
                                   "Mở 1 profile cùng phiên bản bằng tay trong GPM Login để GPM tải nhân về, rồi chạy lại.")
            elif msg == "DownloadProfileFailed":
                # v1.8.9: gặp thật 19/11 (Profile warmup 1/2/3) — GPM không tải được dữ liệu profile về máy
                self.last_error = ("GPM không tải được dữ liệu profile này về máy (DownloadProfileFailed). "
                                   "Mở profile bằng tay trong GPM Login 1 lần (kiểm tra mạng / đồng bộ cloud / "
                                   "dung lượng ổ đĩa), mở được rồi thì chạy lại.")
            else:
                self.last_error = msg or "API không trả link ws"
            return None
            
        except requests.exceptions.RequestException as e:
            print(f"  [-] Lỗi kết nối mạng tới API: {e}")
            self.last_error = f"Không kết nối được GPM API: {e}"
            return None

    def _profile_browser_version(self, profile_id):
        """Lấy 'chrome 155.0.x' của profile (best-effort, '' khi lỗi)."""
        try:
            r = requests.get(f"{self.base_url}/api/v1/profiles/{profile_id}", timeout=3).json()
            b = (r.get("data") or {}).get("browser") or {}
            return f"{b.get('name', '')} {b.get('version', '')}".strip()
        except Exception:
            return ""

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

    def list_groups(self):
        """v1.3.6: kéo DANH SÁCH nhóm profile từ GPM Login (GET /api/v1/groups).

        API thật (dump 15/10/2026, GPM v5.1.1): data.data = [{id, name, sort_order, ...}],
        per_page mặc định 1000 nên một trang là hết. Trả về dict {group_id: tên}
        (rỗng nếu API lỗi — caller coi như không có nhóm, KHÔNG crash).
        """
        try:
            url = f"{self.base_url}/api/v1/groups?page_index=1&page_size=1000"
            response = requests.get(url, timeout=5)
            if response.status_code != 200:
                return {}
            items = (response.json() or {}).get("data", {}).get("data") or []
            return {g.get("id"): (g.get("name") or "").strip()
                    for g in items if g.get("id")}
        except Exception as e:
            print(f"[-] list_groups lỗi: {e}")
            return {}

    def get_proxy_map(self, page_size=50, max_pages=20):
        """v1.8.1: {profile_id: raw_proxy} của MỌI profile (GET /api/v1/profiles phân trang
        bằng `page`). Lỗi -> {} (caller coi như không biết proxy -> không chặn trùng)."""
        out = {}
        try:
            for page in range(1, max_pages + 1):
                url = f"{self.base_url}/api/v1/profiles?page={page}&page_size={page_size}"
                response = requests.get(url, timeout=5)
                if response.status_code != 200:
                    break
                data = (response.json() or {}).get("data", {})
                items = data.get("data") or []
                if not items:
                    break
                for p in items:
                    if p.get("id"):
                        out[p["id"]] = (p.get("raw_proxy") or "").strip()
                if page >= (data.get("last_page") or page):
                    break
        except Exception as e:
            print(f"[-] get_proxy_map lỗi: {e}")
        return out

    def list_profiles(self, page_size=50, max_pages=20):
        """Sprint 1.2: kéo DANH SÁCH profile từ GPM Login (phân trang).

        Trả về list [{"id", "name", "browser", "firefox", "group"}] hoặc None nếu API lỗi.
        browser = tên engine ("chrome"/"firefox"); firefox=True nghĩa CDP không
        dùng được với profile đó (Playwright connect_over_cdp fail) -> UI xám.
        group = TÊN nhóm (API trả group_id UUID; phân giải qua /api/v1/groups —
        dump 15/10/2026). Lỗi/không khớp -> "" (UI gom vào "Chưa có nhóm").
        """
        out = []
        try:
            gmap = self.list_groups()  # v1.3.6: {group_id: tên}; rỗng = không phân nhóm
            # v1.3.6 FIX: GPM v5.1.1 phân trang bằng param "page" (dump 15/10: page_index
            # BỊ BỎ QUA -> mọi trang trả lại trang 1, checklist trùng lặp). Thêm seen-chống-trùng.
            seen = set()
            for page in range(1, max_pages + 1):
                url = f"{self.base_url}/api/v1/profiles?page={page}&page_size={page_size}"
                response = requests.get(url, timeout=5)
                if response.status_code != 200:
                    return out if out else None
                data = (response.json() or {}).get("data", {})
                items = data.get("data") or []
                if not items:
                    break
                for p in items:
                    pid = p.get("id")
                    if not pid or pid in seen:
                        continue
                    seen.add(pid)
                    browser = (p.get("browser") or {}).get("name", "")
                    out.append({
                        "id": pid,
                        "name": p.get("name") or pid[:8],
                        "browser": browser,
                        "firefox": browser.lower() == "firefox",
                        "group": gmap.get(p.get("group_id"), ""),
                        # v1.8.1: proxy thô (ip:port:user:pass) — để lịch chạy chặn trùng IP
                        "proxy": (p.get("raw_proxy") or "").strip(),
                    })
                last_page = data.get("last_page") or page
                if page >= last_page:
                    break
            return out
        except Exception as e:
            print(f"[-] list_profiles lỗi: {e}")
            return out if out else None

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