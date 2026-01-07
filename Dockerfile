FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1         PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends         build-essential         libpq-dev      && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ /app/

# Collect static at build-time (safe even if DB isn't up yet)
RUN python manage.py collectstatic --noinput || true

EXPOSE 8001
CMD ["bash", "-lc", "python manage.py migrate && gunicorn config.wsgi:application -b 0.0.0.0:8000 --workers 3 --timeout 120"]
