import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel

from prompt import SYSTEM_PROMPT

load_dotenv()

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
STATIC_DIR = ROOT / "static"
CACHE_DIR = ROOT / ".cache"
CACHE_PATH = CACHE_DIR / "frames.pkl"
DATA_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

CSV_FILES = {
    "df_employees": "Dim_Employees.csv",
    "df_departments": "Dim_Departments.csv",
    "df_roles": "Dim_Roles.csv",
    "df_attendance": "Fact_Attendance.csv",
    "df_leaves": "Fact_Leaves.csv",
    "df_lifecycle": "Fact_Lifecycle.csv",
}

PREFERRED_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")
FALLBACK_MODEL = "gpt-4o"

app = FastAPI(title="Solid HR Data AI Agent")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

frames: dict[str, pd.DataFrame] = {}


def get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key.startswith("sk-your-key"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY is missing. Add it to the .env file.")
    return OpenAI(api_key=api_key)


def load_csvs() -> None:
    frames.clear()
    for key, filename in CSV_FILES.items():
        path = DATA_DIR / filename
        if path.exists():
            frames[key] = pd.read_csv(path)
    if frames:
        pd.to_pickle(frames, CACHE_PATH)


def schema_summary() -> str:
    if not frames:
        return "No CSV files are loaded yet."
    parts = []
    for key, filename in CSV_FILES.items():
        df = frames.get(key)
        if df is None:
            parts.append(f"{key} ({filename}): NOT LOADED")
            continue
        cols = ", ".join(f"{c} ({df[c].dtype})" for c in df.columns)
        parts.append(f"{key} ({filename}): {len(df)} rows | columns: {cols}")
    return "\n".join(parts)


def run_pandas(code: str) -> str:
    if not frames or not CACHE_PATH.exists():
        return "ERROR: CSV files are not loaded yet. Place them in the data folder and restart the server."

    try:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "pandas_runner.py")],
            input=json.dumps({"code": code, "cache": str(CACHE_PATH)}),
            capture_output=True,
            text=True,
            timeout=90,
        )
    except subprocess.TimeoutExpired:
        return "ERROR: The query timed out. Please ask a simpler or more specific question."

    if proc.returncode != 0:
        err = (proc.stderr or "").strip()[-2000:]
        return (
            "ERROR: The data query crashed. Please rephrase the question.\n"
            + (err or f"Process exited with code {proc.returncode}.")
        )
    output = (proc.stdout or "").strip()
    return output or "Code ran successfully but printed nothing. Print the final DataFrame or number."


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_pandas",
            "description": "Execute Python pandas code against the loaded HR CSVs. Always print() the final result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Executable pandas code. Use df_employees, df_departments, df_roles, df_attendance, df_leaves, df_lifecycle.",
                    }
                },
                "required": ["code"],
            },
        },
    }
]


class ChatRequest(BaseModel):
    message: str
    history: list[dict[str, str]] = []


def complete_with_fallback(client: OpenAI, messages: list[dict[str, Any]], model: str):
    kwargs = {
        "model": model,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
        "temperature": 0.1,
    }
    try:
        return client.chat.completions.create(**kwargs), model
    except Exception as exc:
        err = str(exc).lower()
        if model != FALLBACK_MODEL and ("model" in err or "not found" in err or "invalid" in err):
            kwargs["model"] = FALLBACK_MODEL
            return client.chat.completions.create(**kwargs), FALLBACK_MODEL
        raise exc


@app.on_event("startup")
def startup() -> None:
    load_csvs()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
def status() -> dict[str, Any]:
    files = []
    for key, filename in CSV_FILES.items():
        df = frames.get(key)
        files.append(
            {
                "key": key,
                "filename": filename,
                "loaded": df is not None,
                "rows": int(len(df)) if df is not None else 0,
            }
        )
    return {
        "ready": len(frames) == len(CSV_FILES),
        "loaded_count": len(frames),
        "expected_count": len(CSV_FILES),
        "model": PREFERRED_MODEL,
        "files": files,
    }


@app.post("/api/reload")
def reload_data() -> dict[str, Any]:
    load_csvs()
    return status()


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict[str, Any]:
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message is empty.")
    if not frames:
        load_csvs()
    if len(frames) < len(CSV_FILES):
        missing = [name for key, name in CSV_FILES.items() if key not in frames]
        raise HTTPException(
            status_code=400,
            detail=f"Missing CSV files in the data folder: {', '.join(missing)}",
        )

    client = get_client()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": "Currently loaded data:\n" + schema_summary()},
    ]
    for item in req.history[-8:]:
        role = item.get("role")
        content = item.get("content", "")
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": req.message.strip()})

    used_model = PREFERRED_MODEL
    code_runs: list[str] = []

    for _ in range(4):
        response, used_model = complete_with_fallback(client, messages, used_model)
        choice = response.choices[0]
        if choice.finish_reason != "tool_calls" or not choice.message.tool_calls:
            answer = (choice.message.content or "").strip()
            return {"answer": answer, "model": used_model, "code_runs": code_runs}

        messages.append(choice.message)
        for tool_call in choice.message.tool_calls:
            args = json.loads(tool_call.function.arguments or "{}")
            code = args.get("code", "")
            result = run_pandas(code)
            code_runs.append(code)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }
            )

    return {
        "answer": "I could not finish the analysis after several query attempts. Please rephrase the question.",
        "model": used_model,
        "code_runs": code_runs,
    }
