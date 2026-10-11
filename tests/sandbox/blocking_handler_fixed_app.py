"""Oracle app for the replay harness. Production code does not import this."""

from fastapi import FastAPI

app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/items")
def items():
    return []
