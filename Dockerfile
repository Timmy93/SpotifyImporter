# syntax=docker/dockerfile:1

FROM python:3.14-slim

WORKDIR /app

# Copia solo requirements per mantenere il layer stabile
COPY requirements.txt .

RUN pip3 install --no-cache-dir --user -r requirements.txt \
    && /root/.local/bin/spotdl --download-ffmpeg

# Copia il resto solo dopo
COPY . .

CMD ["python3", "main.py"]
