from fastapi import FastAPI

app = FastAPI()

# uvicorn main:app --reload
# fastapi dev main.py

@app.get("/")
async def root():
    return {"message": "Hello World"}

