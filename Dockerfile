FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=10001:10001 . .
RUN mkdir -p /data /app/uploads \
    && chown -R 10001:10001 /data /app/uploads

USER 10001:10001

EXPOSE 8000

# Inicializa el esquema compatible y luego arranca Gunicorn. SQLite y las
# cargas viven en volúmenes persistentes, fuera de la imagen.
CMD ["sh", "-c", "python -c 'from app import app; from database import init_db; ctx=app.app_context(); ctx.push(); init_db()' && exec gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 4 --access-logfile - --error-logfile - app:app"]
