FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY strategy_original.py cloud_bot.py ./
ENV PYTHONUNBUFFERED=1 STATE_PATH=/data/paper.json
CMD ["python", "cloud_bot.py"]
