FROM python:3.11-slim

WORKDIR /app

# 换源加速 apt
RUN sed -i 's/deb.debian.org/mirrors.ustc.edu.cn/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's/deb.debian.org/mirrors.ustc.edu.cn/g' /etc/apt/sources.list 2>/dev/null || true

# 安装 MediaInfo 系统底层包
RUN apt-get update && apt-get install -y --no-install-recommends \
    mediainfo \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖包 (清华源加速)
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Shanghai

CMD ["python", "main.py"]
