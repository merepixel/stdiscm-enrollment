from fastapi import FastAPI

app = FastAPI(title="Grade Service", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "service": "grade-service"}
