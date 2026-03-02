FROM python:3.10-slim

WORKDIR /app

COPY app.py /app/app.py
COPY templates /app/templates
COPY wheels /wheels

RUN pip install --no-index --find-links=/wheels fastapi uvicorn jinja2

EXPOSE 8088

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8088"]
