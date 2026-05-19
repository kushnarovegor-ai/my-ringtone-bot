FROM python:3.10-slim

# Устанавливаем ffmpeg и системные зависимости
RUN apt-get update && apt-get install -y ffmpeg && apt-get clean && rm -rf /var/lib/apt/lists/*

# Создаем рабочую директорию в контейнере
WORKDIR /app

# Копируем список зависимостей и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем остальной код (наш bot.py)
COPY . .

# Команда для запуска бота
CMD ["python", "bot.py"]
