FROM python:3.10-alpine

ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=on

RUN pip install --upgrade pip && pip install dropbox

RUN mkdir -p /opt
WORKDIR /opt
COPY main.py ./

