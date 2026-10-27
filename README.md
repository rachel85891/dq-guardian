# DQ Guardian

Data-quality agent for CSV tables, built twice: `API/` (hand-written harness on the Messages API) and `SDK/` (Claude Agent SDK). Shared domain code is in `shared/`.

```powershell
python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt; .\.venv\Scripts\pip install -e .
.\.venv\Scripts\python -m pytest -q                       # offline, no key

# API (needs a Console key, set in the terminal only):
$env:ANTHROPIC_API_KEY = "sk-ant-..."
.\.venv\Scripts\python API/main.py --scenario scenario.json --out results/api.json

# SDK (runs on your Claude Code login; the key must NOT be set):
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
.\.venv\Scripts\python SDK/main.py --scenario scenario.json --out results/sdk.json
```

Model `claude-opus-5-5`, effort `medium`, in both versions. Prices in `API/harness/tokens.py` are USD per million tokens; check them against the pricing page.
