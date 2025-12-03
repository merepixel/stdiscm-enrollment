FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY course-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Include service code and shared protos.
COPY course-service/ ./course-service
COPY common/ ./common

WORKDIR /app/course-service

EXPOSE 8002
EXPOSE 50052
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
