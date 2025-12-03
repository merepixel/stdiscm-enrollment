FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY enrollment-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Include service code and shared protos.
COPY enrollment-service/ ./enrollment-service
COPY common/ ./common

WORKDIR /app/enrollment-service

EXPOSE 8003
EXPOSE 50053
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]
