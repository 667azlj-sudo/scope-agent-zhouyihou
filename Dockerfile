# ============ 后端 Dockerfile（FastAPI）============
# 基础镜像：带 Python 3.12 的轻量系统
FROM python:3.12-slim

# 工作目录
WORKDIR /app

# 数据持久化目录（docker-compose 挂载卷到 /app/data）
ENV DATA_DIR=/app/data
RUN mkdir -p /app/data

# 先拷贝依赖清单，安装依赖（利用 Docker 缓存，改代码不用重装依赖）
COPY requirements.txt .
RUN pip install -r requirements.txt --no-cache-dir

# 拷贝项目代码
COPY . .

# 暴露 8000 端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
