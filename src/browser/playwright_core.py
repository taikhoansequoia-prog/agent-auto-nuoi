from playwright.sync_api import sync_playwright

class BrowserController:
    def __init__(self, ws_endpoint):
        """
        Khởi tạo bộ điều khiển Playwright với wsEndpoint lấy từ AntidetectAPI.
        """
        self.ws_endpoint = ws_endpoint
        self.playwright_context = None
        self.browser = None
        self.page = None

    def connect(self):
        """
        Gắn Playwright vào trình duyệt đã mở qua giao thức CDP.
        """
        print("[*] Đang kết nối Playwright với trình duyệt...")
        self.playwright_context = sync_playwright().start()
        
        # Kết nối qua WebSocket
        self.browser = self.playwright_context.chromium.connect_over_cdp(self.ws_endpoint)
        
        # Lấy context và page đầu tiên có sẵn
        contexts = self.browser.contexts
        if not contexts:
            print("[-] Không tìm thấy context nào.")
            return False
            
        context = contexts[0]
        self.page = context.pages[0] if context.pages else context.new_page()
        
        print("[+] Kết nối Playwright thành công!")
        return True

    def goto_url(self, url):
        """
        Điều hướng trang web
        """
        if self.page:
            print(f"[*] Đang truy cập: {url}")
            self.page.goto(url)
            # SỬA DÒNG NÀY: Dùng "load" thay vì "networkidle"
            self.page.wait_for_load_state("load")
            
    def take_screenshot(self, save_path="current_view.png"):
        """
        Chụp ảnh màn hình toàn bộ trang để chuẩn bị gửi cho Gemini
        """
        if self.page:
            self.page.screenshot(path=save_path, full_page=True)
            print(f"[+] Đã lưu ảnh chụp màn hình tại: {save_path}")
            return save_path
        return None

    def close(self):
        """
        Ngắt kết nối Playwright (lưu ý: không đóng hẳn trình duyệt, 
        việc đóng hẳn sẽ do API của Antidetect lo).
        """
        if self.browser:
            self.browser.close()
        if self.playwright_context:
            self.playwright_context.stop()
        print("[+] Đã ngắt kết nối Playwright.")

    def mark_elements(self):
        """
        Gắn ID độc quyền cho các phần tử và vẽ khung đỏ.
        """
        if not self.page:
            return False

        print("[*] Đang vẽ Bounding Box lên các phần tử tương tác...")
        
        js_code = """
        () => {
            let elements = document.querySelectorAll('button, a, input, select, textarea, [role="button"]');
            let counter = 1;
            
            document.querySelectorAll('.ai-bounding-box').forEach(e => e.remove());

            elements.forEach((el) => {
                let rect = el.getBoundingClientRect();
                
                if (rect.width > 0 && rect.height > 0 && rect.top >= 0 && rect.left >= 0) {
                    let boxId = 'ai-mark-' + counter++;
                    
                    // GẮN ID THỰC TẾ VÀO ELEMENT ĐÓ
                    el.setAttribute('data-ai-id', boxId);
                    
                    // Vẽ khung (Giữ nguyên như cũ)
                    let box = document.createElement('div');
                    box.className = 'ai-bounding-box';
                    box.style.position = 'fixed';
                    box.style.border = '2px solid red';
                    box.style.top = rect.top + 'px';
                    box.style.left = rect.left + 'px';
                    box.style.width = rect.width + 'px';
                    box.style.height = rect.height + 'px';
                    box.style.zIndex = '999999';
                    box.style.pointerEvents = 'none';
                    
                    // Vẽ nhãn (Dùng số cho gọn ảnh, nhưng ID là ai-mark-số)
                    let label = document.createElement('span');
                    label.innerText = boxId.replace('ai-mark-', '');
                    label.style.position = 'absolute';
                    label.style.background = 'red';
                    label.style.color = 'white';
                    label.style.fontSize = '14px';
                    label.style.fontWeight = 'bold';
                    label.style.padding = '2px 4px';
                
                    label.style.top = '0px'; 
                    label.style.left = '0px';   
                    
                    box.appendChild(label);
                    document.body.appendChild(box);
                }
            });
            return true;
        }
        """
        self.page.evaluate(js_code)
        return True
    def remove_marks(self):
        """
        Xóa toàn bộ các khung viền đỏ và nhãn số khỏi trang web để phi tang dấu vết.
        (Lưu ý: Không xóa thuộc tính data-ai-id để Playwright vẫn click được)
        """
        if self.page:
            print("[*] Đang phi tang dấu vết (Xóa Bounding Boxes)...")
            js_cleanup = """
            () => {
                document.querySelectorAll('.ai-bounding-box').forEach(e => e.remove());
            }
            """
            self.page.evaluate(js_cleanup)    
    def click_by_ai_id(self, box_id_number):
        """Playwright sẽ tự tìm element có chứa thuộc tính data-ai-id và click"""
        if self.page:
            target_id = f"ai-mark-{box_id_number}"
            print(f"[*] Đang tìm và click vào Element có ID: {target_id}")
            
            # Sử dụng cú pháp selector CSS của Playwright
            target_element = self.page.locator(f"[data-ai-id='{target_id}']")
            
            if target_element.count() > 0:
                # scroll_into_view_if_needed: Tự động cuộn trang nếu nút bị che lấp
                target_element.scroll_into_view_if_needed()
                target_element.click()
                print("[+] Click thành công 100%!")
            else:
                print(f"[-] Không tìm thấy Element mang ID: {target_id}")