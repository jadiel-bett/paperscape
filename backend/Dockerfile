FROM python:3.12.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

RUN groupadd --gid 10001 paperscape \
    && useradd --uid 10001 --gid 10001 --create-home \
       --shell /usr/sbin/nologin paperscape \
    && install -d -o 10001 -g 10001 /data

COPY app ./app

USER paperscape

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]