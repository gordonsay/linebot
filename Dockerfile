# 選擇 Python 3.10.12 slim 版本（更輕量）
FROM python:3.10.12-slim

# 設置工作目錄
WORKDIR /app

# 安裝系統依賴（Playwright 需要的）
RUN apt-get update && apt-get install -y \
    curl wget unzip libnss3 libatk1.0-0 libxcomposite1 \
    libxrandr2 libxdamage1 libxkbcommon0 libasound2 \
    libpangocairo-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 複製依賴文件並安裝
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y ffmpeg


# 安裝 Playwright 依賴
RUN python -m playwright install --with-deps

# 複製應用程式
COPY . .

# Render 會自動設定 `PORT`，這裡只是預設
ENV PORT 5000

# 暴露端口（Render 會自動映射）
EXPOSE 5000

# 以 Gunicorn 啟動 Flask 應用
CMD ["gunicorn", "-b", "0.0.0.0:${PORT}", "main:app"]
