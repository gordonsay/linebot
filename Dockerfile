# 使用官方 Playwright Python 版本（使用 bullseye-slim 以減少體積）
FROM mcr.microsoft.com/playwright/python:latest

# 設置工作目錄
WORKDIR /app

# 複製依賴文件並安裝
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安裝 Playwright 瀏覽器依賴
RUN playwright install --with-deps

# 複製所有程式碼
COPY . .

# 暴露應用程序的端口（根據你的 Flask 或 FastAPI 設定）
EXPOSE 8000

# 啟動應用
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "main:app"]
