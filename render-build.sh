#!/usr/bin/env bash
# 发生错误时立即退出
set -o errexit

# 安装 Python 依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install --with-deps
