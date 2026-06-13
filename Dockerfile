FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Папка для .session файлов (монтируется как volume в compose).
RUN mkdir -p /app/sessions

CMD ["python", "bot.py"]
