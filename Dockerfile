FROM python:3.12-slim

# Не создавать .pyc файлы
ENV PYTHONDONTWRITEBYTECODE=1
# Не буферизовать stdout/stderr
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Системные зависимости
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# Зависимости Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Код приложения
COPY . .

# Порт для webhook
EXPOSE 8080

# Запуск
CMD ["python", "main.py"]