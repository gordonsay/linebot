# 使用官方 Python 3.11 Slim 版本
FROM python:3.11-slim

# 設置工作目錄
WORKDIR /app

# 安裝系統依賴（Playwright 必要的套件）
RUN apt-get update && apt-get install -y \
    curl wget unzip libnss3 libatk1.0-0 libxcomposite1 \
    libxrandr2 libxdamage1 libxkbcommon0 libasound2 \
    libpangocairo-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 安裝 Python 依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安裝 Playwright 及其瀏覽器
RUN pip install --no-cache-dir playwright
RUN playwright install --with-deps

# 複製所有程式碼
COPY . .

# 設置開放端口
EXPOSE 5000

# 啟動應用
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000"]
