#!/usr/bin/env bash
set -o errexit  # 發生錯誤時立即退出

STORAGE_DIR=/opt/render/project/.render/chrome
CHROME_DEB_URL="https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb"

# 確保安裝目錄存在
mkdir -p "$STORAGE_DIR"

# 下載 Chrome
echo "Downloading Google Chrome..."
wget -O "$STORAGE_DIR/chrome.deb" "$CHROME_DEB_URL"

# 解壓 Chrome，而不使用 `sudo dpkg -i`
echo "Extracting Chrome..."
dpkg -x "$STORAGE_DIR/chrome.deb" "$STORAGE_DIR"

# 移除下載的安裝包
rm "$STORAGE_DIR/chrome.deb"

# 確保 Chrome 可執行
echo "Chrome Installed at: $STORAGE_DIR"
ls -l "$STORAGE_DIR"

# 安裝 Python 依賴
if [[ -f "requirements.txt" ]]; then
    pip install -r requirements.txt
else
    echo "ERROR: requirements.txt not found! Exiting..."
    exit 1
fi
