FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY grade-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Include service code and shared protos.
COPY grade-service/ ./grade-service
COPY common/ ./common

WORKDIR /app/grade-service

EXPOSE 8004
EXPOSE 50054
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004"]
