#!/usr/bin/env bash
# 发生错误时立即退出
set -o errexit

# 定义存储 Chrome 的目录（Render 提供的持久化存储路径）
STORAGE_DIR=/opt/render/project/.render

# 安裝 Chrome（移除 `sudo`）
echo "Installing Google Chrome..."
wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add -  # 移除 sudo
sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'
apt-get update
apt-get install -y google-chrome-stable  # 移除 sudo

# 確保 binary 可用
echo "Chrome Version:"
google-chrome-stable --version


# 检查 Chrome 是否已经安装
if [[ ! -d $STORAGE_DIR/chrome ]]; then
    echo "正在下载并安装 Google Chrome..."
    mkdir -p $STORAGE_DIR/chrome
    cd $STORAGE_DIR/chrome

    # 下载最新版本的 Chrome
    wget -P ./ https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
    
    # 解压 Chrome 安装包（不使用 `dpkg -i` 以避免依赖问题）
    dpkg -x ./google-chrome-stable_current_amd64.deb $STORAGE_DIR/chrome
    
    # 删除安装包
    rm ./google-chrome-stable_current_amd64.deb
    echo "Google Chrome 安装完成！"
else
    echo "使用缓存中的 Google Chrome。"
fi

# 确保当前路径包含 requirements.txt
if [[ ! -f "requirements.txt" ]]; then
    echo "ERROR: requirements.txt not found! Exiting..."
    exit 1
fi

# 安装 Python 依赖
pip install -r requirements.txt
