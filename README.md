# Solid HR Data AI Agent

A basic HR analytics chatbot for **Solid**. It answers questions about headcount, PTO liability, resignation risk, pay equity, and overtime by querying six CSV files with Pandas, then returning a business-friendly summary.

The UI is a simple chat page. The backend uses OpenAI **gpt-4.1** (fallback: **gpt-4o**) with your HR system prompt.

## Requirements

- Python 3.11+ (3.14 works)
- An OpenAI API key

## Project layout

```
app.py              # FastAPI backend and Pandas sandbox
prompt.py           # HR agent system prompt
static/             # Chat frontend
data/               # Place the 6 CSV files here
.env                # OPENAI_API_KEY (not committed)
.env.example        # Template for environment variables
requirements.txt
```

## Setup

1. Open a terminal in this project folder.

2. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Create a `.env` file in the project root (copy `.env.example`) and add your key:

```
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4.1
```

Do not commit `.env` or paste the key into the frontend.

## Load the database (6 CSV files)

The agent expects these **exact filenames**:

| File | Role |
| --- | --- |
| `Dim_Employees.csv` | Employee profiles |
| `Dim_Departments.csv` | Departments |
| `Dim_Roles.csv` | Jobs / roles |
| `Fact_Attendance.csv` | Daily attendance and overtime |
| `Fact_Leaves.csv` | Leaves |
| `Fact_Lifecycle.csv` | Career events (promotion, resignation, etc.) |

Put the files in the `data/` folder. The chat UI only reads from that folder (there is no upload button).

Chat is blocked until all six files are present.

## Run the chatbot

```bash
source .venv/bin/activate
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## How to use it

1. Confirm the sidebar shows **Data ready** (6/6 files).
2. Type a question, or click one of the sample prompts.
3. The agent writes Pandas code, runs it on your CSVs, and replies with numbers plus a short business interpretation. The executed query appears under the answer.

Example questions:

- What is the total financial liability of unused PTO days for active employees, broken down by department?
- What is the pay gap percentage between mothers and men with the same job titles in the R&D department?
- Which managers have the highest team overtime and termination risk?

## Business rules used by the agent

- Current metrics use **active** employees (`Status = 'Active'`).
- PTO liability = `(Current_Salary / 22) * PTO_Balance`. Balance over 20 is high risk.
- Resignation risk is tied to overtime, commute distance, and `WFH_Days = 0`.
- Pay gap comparisons are grouped by `Job_Title` or `Role_Category`.

## Troubleshooting

- **Missing CSV files:** filenames must match the table above, including capitalization.
- **OPENAI_API_KEY is missing:** check that `.env` is in the project root and restart the server.
- **Model error:** the app tries `gpt-4.1` first, then `gpt-4o`. You can set `OPENAI_MODEL` in `.env`.
- **Port already in use:** stop the other process on port 8000, or run with `--port 8001`.
