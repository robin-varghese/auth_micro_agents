from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import os

app = FastAPI()

# Database Setup
DB_FILE = "calculator.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  expression TEXT, 
                  result REAL, 
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

# Models
class Calculation(BaseModel):
    expression: str

# API Routes
@app.post("/api/calculate")
async def calculate(calc: Calculation):
    try:
        # Basic validation
        allowed_chars = "0123456789+-*/(). "
        if not all(c in allowed_chars for c in calc.expression):
             raise HTTPException(status_code=400, detail="Invalid characters")
        
        # Safe evaluation (ish)
        result = eval(calc.expression)
        
        # Save to DB
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO history (expression, result) VALUES (?, ?)", (calc.expression, result))
        conn.commit()
        conn.close()
        
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/history")
async def get_history():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT expression, result, created_at FROM history ORDER BY id DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()
    return [{"expression": row["expression"], "result": row["result"], "created_at": row["created_at"]} for row in rows]

# Serve Static UI (Must be mounted last to catch root)
app.mount("/", StaticFiles(directory="../ui", html=True), name="ui")
