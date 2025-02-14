# 選擇 Python 3.10.12 slim 版本（更輕量）
FROM python:3.10.12-slim

# 設置工作目錄
WORKDIR /app

# 安裝系統依賴（Playwright + FFmpeg）
RUN apt-get update && apt-get install -y \
    curl wget unzip libnss3 libatk1.0-0 libxcomposite1 \
    libxrandr2 libxdamage1 libxkbcommon0 libasound2 \
    libpangocairo-1.0-0 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 複製依賴文件並安裝
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安裝 Playwright（僅安裝 Chromium，減少映像大小）
RUN python -m playwright install chromium --with-deps

# 複製應用程式
COPY . .

# 設定環境變數
ENV PORT 5000

# 暴露端口（Render 會自動映射）
EXPOSE 5000

# 使用 Uvicorn 啟動 Flask 應用
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "2", "-b", "0.0.0.0:5000", "main:app"]

