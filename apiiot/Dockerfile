FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install  -y gcc && \
    rm -rf /var/lib/apt/lists/*

ENV TZ="America/Argentina/Buenos_Aires"

COPY ./requirements.txt /app/requirements.txt

RUN pip install --upgrade pip

RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

COPY . /app

CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "-b", ":8002", "app:app"]
