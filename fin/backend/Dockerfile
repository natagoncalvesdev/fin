FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY frontend /frontend

ENV DATABASE_URL=postgresql://fin:fin@db:5432/fin

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
