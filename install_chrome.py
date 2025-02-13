from playwright.sync_api import sync_playwright

# 自動安裝 Playwright 內建 Chromium
def install_playwright_chrome():
    print("📥 安裝 Playwright 內建 Chromium...")
    with sync_playwright() as p:
        p.install()

if __name__ == "__main__":
    install_playwright_chrome()
