#!/bin/bash

# 更新套件列表
apt-get update

# 安裝系統相依性 (Chromium 需要的 libraries)
apt-get install -y --no-install-recommends \
    libxtst6 \
    libxrender1 \
    libxi6 \
    libxrandr2 \
    # ... 其他相依性 ...

# 安裝 Python 相依性
pip install -r requirements.txt

# 安裝 Node.js (Playwright 需要 Node.js)
curl -fsSL https://deb.nodesource.com/setup_16.x | bash -
apt-get install -y nodejs

# 安裝 Playwright
npm install -g playwright

# 安裝 Chromium
playwright install --with-deps chromium

# 快取 Playwright 瀏覽器 (可選，加速部署)
if [ ! -d ~/.cache/playwright ]; then
  playwright install --with-deps chromium
fi

# 啟動應用程式
python your_app.py  # 或 gunicorn, uwsgi 等