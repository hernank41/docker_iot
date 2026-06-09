FROM python:3.11-slim

WORKDIR /app

ENV TZ="America/Argentina/Buenos_Aires"

COPY ./requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

COPY . /app

# --proxy-headers confía en las cabeceras de Nginx (X-Forwarded-*)
CMD ["hypercorn", "--bind", "0.0.0.0:8000", "--workers", "4", "crud:app"]