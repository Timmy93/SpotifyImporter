# syntax=docker/dockerfile:1

FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt requirements.txt

RUN pip3 install --user -r requirements.txt && \
    spotdl --download-ffmpeg

COPY . .

CMD [ "python3", "main.py"]