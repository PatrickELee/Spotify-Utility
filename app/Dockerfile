ARG PYTHON_VERSION=3.11.4
FROM python:${PYTHON_VERSION}-slim as base

WORKDIR /app

COPY ./requirements.txt /app
COPY /app /app

RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    python -m pip install -r requirements.txt

EXPOSE 5000

CMD flask run --host=0.0.0.0
