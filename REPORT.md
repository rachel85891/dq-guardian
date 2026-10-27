# DQ Guardian: one agent, two harnesses

**Status: the API column is not measured yet.** `results/sdk.json` comes from a real run on a Claude Code login.
`results/api.json` needs an Anthropic Console key and has not been produced; the API harness was verified only
against a scripted fake client (61 offline tests). Everything marked **n/a** below must be filled from
`results/api.json` (`python API/main.py --scenario scenario.json --out results/api.json`).

Both versions: `claude-opus-5-5`, effort `medium`, same `shared/` tools, same `scenario.json`, pinned libraries
(`requirements.txt`), state reset before each run.

## Agent
DQ Guardian checks CSV tables for data-quality problems. Eight tools (`shared/domain.py`); the external one reads
CSV files from disk on every call. Memory keeps facts across sessions; a contradicting fact supersedes the old one
instead of overwriting it (old value is kept, marked inactive), so the contradiction is checkable from state.

## Scenario (8 turns, 2 sessions)
Session 1: profile `orders`, add three rules and run the check, remember owner and `severity_threshold=high`,
log a high incident. Between sessions the CSV is replaced with the next day's file. Session 2 (new agent instance):
recall, re-run checks on the new file, **contradiction** (`severity_threshold` high to medium), log a medium incident,
list incidents.

State-based checks (`shared/checks.py`): rules saved; contradiction replaced not duplicated (one active value,
old one superseded); incidents have the right severities; the check output changed after the CSV swap; the saved
owner is in persisted memory and was repeated in session 2; history continued in the new instance.
Each check has a negative test proving it can fail (`tests/test_checks.py`).

## Results

| | API | SDK |
|---|---|---|
| Checks passed | n/a | 6/6 |
| Model calls | n/a | 17 |
| Input (uncached) tokens | n/a | 34 |
| Cache read tokens | n/a | 71,631 |
| Cache write tokens | n/a | 6,668 |
| Output tokens | n/a | 3,299 |
| Cache hit (read / all prompt tokens) | n/a | 91.4% |
| Cost (USD) | n/a | 0.707 (`total_cost_usd`, from Claude Code) |

SDK per turn (calls / cache read / cache write / output / USD): the prompt grows from about 2k to 12.8k cached
tokens by turn 8, and cost per turn rises from 0.030 to 0.134, which is the cost of carrying the whole history.

## Harness lines of code (code only: no blanks, comments or docstrings)

| Part | API (`API/harness/*.py`) | SDK (lines marked `# replaces:`) |
|---|---|---|
| loop | 52 | 1 |
| tools | 23 | 3 |
| history | 32 | 1 |
| memory | 14 | 2 |
| context | 12 | 1 |
| compaction | 20 | 0 (automatic) |
| caching | 17 | 0 (automatic) |
| tokens | 28 | 1 |
| **Total** | **198** | **9 marked** (113 lines of SDK config in all, incl. tool wrappers) |

The SDK counts are lines carrying a marker, so they are a lower bound for what each part would be if written out.

## Analysis
Hypotheses until `api.json` exists; replace with measurements.

- **Where the SDK should cost more tokens:** Claude Code adds its own system prompt and tool-calling scaffolding
  to every request (the first SDK turn already carries about 4.2k prompt tokens, 1,973 read + 2,236 written, even with
  built-in tools disabled). The API harness controls the prompt exactly: our short system prompt plus eight tool
  schemas, to be measured in `api.json`.
- **Where the SDK should cost less:** cache breakpoints are placed automatically and well (91.4% hit rate with no
  code from us). The hand-written API harness has to prove it does at least as well.
- **Context engineering:** the API harness injects only the facts relevant to the turn (`memory.py`, `context.py`).
  In the SDK, relevant facts come from `CLAUDE.md` (all of them) plus the resumed session, and the model pulls the
  rest with `recall`. Risk in the API version: an old fact stays in an earlier user message after it is superseded.
- **Control gained with the API:** exact prompt contents, where cache breakpoints go, when to compact, what happens on
  `max_tokens` / refusal / step limit, what is stored in history (thinking blocks verbatim), per-call usage.
- **Control lost with the SDK:** all of the above; cost reporting is Claude Code's, not ours; model-call counts are
  inferred from assistant message ids.
- **Which one I would pick:** not decided without the API numbers. Prior: SDK for a personal tool (9 marked lines versus
  198, equal check results); API if token cost or exact context control matters.

## Known limits
- API harness never ran against the real API (`tests/test_live_contract.py` is written and skipped without a key).
- API prices in `tokens.py` are USD per million tokens, cache-write rate assumed to be 1.25x input; the SDK reports
  its own cost, so the cost columns may not be like for like.
- CSVs are loaded fully into memory; JSON state is single-process.
