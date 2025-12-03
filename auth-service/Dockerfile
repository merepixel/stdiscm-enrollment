FROM python:3.12-slim

WORKDIR /app

COPY auth-service/requirements.txt ./auth-service/requirements.txt
RUN pip install --no-cache-dir -r auth-service/requirements.txt

COPY auth-service/ ./auth-service
COPY common/ ./auth-service/common

WORKDIR /app/auth-service

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]