from fastapi import FastAPI

app = FastAPI()

# uvicorn main:app --reload
# fastapi dev main.py
# uvicorn main:app --host 0.0.0.0 --port 10000

@app.get("/")
async def root():
    return {"message": "Hello World 2"}

