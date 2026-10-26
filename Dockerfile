FROM python:3.12-slim
# libraqm ضروري لتشكيل الحروف العربية تشكيلًا صحيحًا
RUN apt-get update && apt-get install -y --no-install-recommends libraqm0 libfribidi0 libharfbuzz0b \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8000
EXPOSE 8000
CMD ["python", "server.py"]
