# syntax=docker/dockerfile:1

FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt requirements.txt

RUN RUN apt-get -y update && \
    DEBIAN_FRONTEND=noninteractive && \
    apt-get install --no-install-recommends -y ffmpeg && \
    pip3 install --user -r requirements.txt

COPY . .

CMD [ "python3", "main.py"]