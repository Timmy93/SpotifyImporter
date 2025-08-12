# syntax=docker/dockerfile:1

FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt requirements.txt

RUN apt-get -y update && \
    apt-get -y upgrade &&  \
    apt-get install -y ffmpeg && \
    pip3 install --user -r requirements.txt

COPY . .

CMD [ "python3", "main.py"]