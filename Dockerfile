# 使用官方的 Playwright 基础镜像
FROM mcr.microsoft.com/playwright/python:v1.50.0-focal

# 设置工作目录
WORKDIR /app

# 复制项目文件到容器中
COPY . /app/

# 安装 Python 依赖项
RUN pip install --no-cache-dir -r requirements.txt

# 设置环境变量以指定浏览器的安装路径
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# 安装 Playwright 浏览器及其依赖项
RUN playwright install --with-deps

# 暴露应用程序运行的端口（如果适用）
EXPOSE 8000

# 运行应用程序
CMD ["python", "main.py"]
