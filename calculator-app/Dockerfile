FROM python:3.11-slim

WORKDIR /app

# 1. Install Backend Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. Copy Code
# Copy Backend into /app/backend
COPY backend ./backend
# Copy UI into /app/ui
COPY ui ./ui

# 3. Validation (Optional)
RUN ls -R /app

# 4. Run Application
# We change directory to backend so relative path "../ui" works in main.py
WORKDIR /app/backend

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
