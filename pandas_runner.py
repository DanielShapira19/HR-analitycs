import io
import json
import sys
import traceback
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import pandas as pd

BLOCKED = ("__import__", "import ", "open(", "exec(", "eval(", "os.", "sys.", "subprocess", "pathlib", "shutil")


def main() -> None:
    payload = json.load(sys.stdin)
    code = payload.get("code") or ""
    cache_path = Path(payload["cache"])

    for token in BLOCKED:
        if token in code:
            print(f"ERROR: The code is not allowed to use '{token.strip()}'.")
            return

    frames = pd.read_pickle(cache_path)
    sandbox = {
        "pd": pd,
        "np": np,
        "df_employees": frames.get("df_employees"),
        "df_departments": frames.get("df_departments"),
        "df_roles": frames.get("df_roles"),
        "df_attendance": frames.get("df_attendance"),
        "df_leaves": frames.get("df_leaves"),
        "df_lifecycle": frames.get("df_lifecycle"),
    }

    stdout = io.StringIO()
    try:
        with redirect_stdout(stdout):
            exec(code, sandbox, sandbox)
    except Exception:
        print("ERROR while running pandas code:\n" + traceback.format_exc(limit=4))
        return

    output = stdout.getvalue().strip()
    if not output:
        result = sandbox.get("result")
        output = str(result) if result is not None else "Code ran successfully but printed nothing. Print the final DataFrame or number."
    if len(output) > 12000:
        output = output[:12000] + "\n... (truncated)"
    print(output)


if __name__ == "__main__":
    main()
