FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY requirements-full.txt requirements.txt ./
RUN pip install --no-cache-dir -r requirements-full.txt
COPY . .
EXPOSE 8000
CMD ["sh", "-c", "python -m app.db_init && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
