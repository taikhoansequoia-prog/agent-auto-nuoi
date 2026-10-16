"""
BrowserFactory - Module hợp nhất GPM Login và BitBrowser vào một interface chung.
UI và worker chỉ cần gọi BrowserFactory.get_api(browser_type) để lấy đúng API client.
"""

from src.browser.antidetect import AntidetectAPI
from src.browser.bitbrowser_api import BitBrowserAPI


# Hằng số định danh loại browser
BROWSER_GPM = "gpm"
BROWSER_BITBROWSER = "bitbrowser"


class BrowserFactory:
    """Factory tạo đúng API client dựa trên loại browser được chọn."""

    @staticmethod
    def get_api(browser_type=BROWSER_GPM, **kwargs):
        """
        Trả về instance API tương ứng với loại browser.

        Args:
            browser_type: "gpm" hoặc "bitbrowser"
            **kwargs: Tham số truyền vào constructor của API (port, base_url...)

        Returns:
            AntidetectAPI hoặc BitBrowserAPI instance
        """
        if browser_type == BROWSER_GPM:
            base_url = kwargs.get("base_url", "http://localhost:9495")
            return AntidetectAPI(base_url=base_url)

        elif browser_type == BROWSER_BITBROWSER:
            port = kwargs.get("port", 54345)
            return BitBrowserAPI(port=port)

        else:
            raise ValueError(f"Loại browser không hỗ trợ: {browser_type}. "
                             f"Chỉ chấp nhận '{BROWSER_GPM}' hoặc '{BROWSER_BITBROWSER}'.")

    @staticmethod
    def get_available_types():
        """Trả về danh sách các loại browser đang hỗ trợ."""
        return [
            {"id": BROWSER_GPM, "name": "GPM Login", "default_port": 9495},
            {"id": BROWSER_BITBROWSER, "name": "BitBrowser", "default_port": 54345},
        ]
