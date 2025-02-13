import os
import subprocess

# 定義 Chrome 存放目錄
CHROME_DIR = "/opt/render/project/.render/chrome"
CHROME_BIN = os.path.join(CHROME_DIR, "chrome")

# 如果 Chrome 已經存在，則跳過下載
if os.path.exists(CHROME_BIN):
    print("✅ Chrome 已安裝，跳過下載。")
else:
    print("📥 下載並安裝 Google Chrome...")
    os.makedirs(CHROME_DIR, exist_ok=True)

    # 下載 Chrome
    subprocess.run(
        [
            "wget", "-q", "-O", "chrome.deb",
            "https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb"
        ],
        check=True
    )

    # 解壓 Chrome 安裝包（Render 無法 `dpkg -i`，所以手動解壓）
    subprocess.run(["dpkg", "-x", "chrome.deb", CHROME_DIR], check=True)

    # 刪除下載的安裝包
    os.remove("chrome.deb")
    print("✅ Chrome 安裝完成！")

# 輸出 Chrome 版本
subprocess.run([CHROME_BIN, "--version"])
