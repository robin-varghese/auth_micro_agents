FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

EXPOSE 6001

CMD ["gunicorn", "--bind", "0.0.0.0:6001", "--workers", "2", "--timeout", "60", "server:app"]
