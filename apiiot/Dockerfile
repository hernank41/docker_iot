FROM python:3.11-slim

WORKDIR /app

ENV TZ="America/Argentina/Buenos_Aires"

COPY ./asyncmy-0.2.7-cp311-cp311-manylinux_2_31_aarch64.whl /app/asyncmy-0.2.7-cp311-cp311-manylinux_2_31_aarch64.whl
COPY ./requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt && \
    rm -rf /app/asyncmy-0.2.7-cp311-cp311-manylinux_2_31_aarch64.whl

COPY . /app

CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "-b", ":8002", "app:app"]
