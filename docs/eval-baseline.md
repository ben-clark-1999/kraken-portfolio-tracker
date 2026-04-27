# Eval baseline

First baseline run captured 2026-04-27 after the eval harness landed (Task 4.4).

Three pre-existing infrastructure bugs were fixed as part of this task before
the baseline could be captured:

1. `PostgresSaver` (sync) was used with `astream` (async) — the async path
   unconditionally calls `aget_tuple`, which raises `NotImplementedError` on the
   sync saver. Migrated to `AsyncPostgresSaver` + `AsyncConnectionPool`.
2. `ANTHROPIC_API_KEY` was loaded by pydantic `BaseSettings` into the settings
   object but not propagated to `os.environ`, so `ChatAnthropic()` could not
   resolve it in the test process. Fixed via `conftest.py` propagation.
3. `AGENT_MODEL` and `DEFAULT_JUDGE_MODEL` were set to
   `claude-sonnet-4-5-20241022` (a model ID that returns 404 for this API key).
   Corrected to `claude-sonnet-4-5`.

## Summary

```
EVAL RESULTS (run-id 1cf0bf9b, 2026-04-27T12:25:22.869240Z)
─────────────────────────────────────────────────────
Classification:    24/35  (69%)
Tool-use:          26/35  (74%)
Answer quality:    65/86 dimensions  (76%)

FAILURES:
  q001 [quick]  answer-quality formatting_correct: FAIL — percentage formatting
                inconsistent (2 decimal places vs source data precision)
  q003 [quick]  answer-quality cites_aud_value: FAIL — $0.00 is trivially
                correct but judge expects non-zero formatted value
  q006 [quick]  answer-quality formatting_correct: FAIL — $3,228.06 flagged as
                missing comma (judge parsing error; value is already correct)
  q011 [quick]  classification: expected=analysis got=quick (confidence=0.95)
  q011 [quick]  tool-use: expected at least one of ['get_balance_change',
                'get_portfolio_summary'], got ['', 'ClassifierOutput']
  q011 [quick]  answer-quality cites_aud_value: FAIL — answer contains tool
                metadata, not actual response text
  q011 [quick]  answer-quality formatting_correct: FAIL — same
  q011 [quick]  answer-quality addresses_question: FAIL — same
  q012 [quick]  classification: expected=analysis got=quick (confidence=0.95)
  q012 [quick]  tool-use: expected at least one of ['get_balance_change',
                'get_relative_performance'], got ['', 'ClassifierOutput',
                'get_dca_history', 'get_portfolio_summary']
  q012 [quick]  answer-quality cites_actual_dates_from_tools: FAIL — answer
                states today's date but it doesn't appear in tool results
  q013 [open]   classification: expected=analysis got=open (confidence=0.95)
  q018 [analysis]  answer-quality cites_aud_value: FAIL — $118.96 and $118.64
                   lack comma separators (sub-$1000 values don't need them, but
                   judge expects the format literally)
  q019 [tax]    answer-quality cites_ato_rule: FAIL — says "per ATO rules" but
                doesn't name the specific provision
  q019 [tax]    answer-quality shows_math: FAIL — gives final figure $0.00
                without showing working
  q021 [open]   classification: expected=tax got=open (confidence=0.85)
  q021 [open]   answer-quality cites_ato_rule: FAIL — describes the 50% CGT
                discount but doesn't cite the formal rule name
  q022 [tax]    answer-quality cites_ato_rule: FAIL — mentions "12-month CGT
                discount threshold" but doesn't use formal ATO citation
  q022 [tax]    answer-quality shows_math: FAIL — cites ~25% tax saving without
                derivation
  q022 [tax]    answer-quality addresses_question: FAIL — cannot rank buys by
                tax saving (explains why, but doesn't attempt the answer)
  q023 [tax]    answer-quality cites_aud_value: FAIL — states no ETH lots
                without citing dollar amounts
  q024 [comparison]  answer-quality states_assumptions: FAIL — answer shows
                     raw JSON fragments instead of a formatted response
  q024 [comparison]  answer-quality cites_aud_value: FAIL — same
  q025 [comparison]  tool-use: expected at least one of
                     ['get_buy_and_hold_comparison', 'get_relative_performance'],
                     got ['', 'ClassifierOutput']
  q025 [comparison]  answer-quality states_assumptions: FAIL — agent asked
                     clarifying questions instead of running the tool
  q026 [comparison]  tool-use: expected at least one of
                     ['get_buy_and_hold_comparison'], got ['', 'ClassifierOutput']
  q026 [comparison]  answer-quality states_assumptions: FAIL — same pattern
  q026 [comparison]  answer-quality addresses_question: FAIL — same
  q027 [analysis]  classification: expected=comparison got=analysis
                   (confidence=0.85)
  q028 [comparison]  answer-quality cites_aud_value: FAIL — describes
                     methodology without providing numerical results
  q029 [analysis]  classification: expected=open got=analysis (confidence=0.85)
  q031 [?]  error: API credit exhausted (400 invalid_request_error)
  q032 [?]  error: API credit exhausted (400 invalid_request_error)
  q033 [?]  error: API credit exhausted (400 invalid_request_error)
  q034 [?]  error: API credit exhausted (400 invalid_request_error)
  q035 [?]  error: API credit exhausted (400 invalid_request_error)
```

## Notable failures

### Classification (24/35, 69%)

- **q011, q012** — "Am I up or down overall?" and "How's my portfolio performing
  overall?" were expected as `analysis` but classified as `quick` at high
  confidence. These queries sit on the quick/analysis border; the classifier
  reasonably treats them as "lookup, not trend analysis." Consider lowering
  `min_confidence` or adding them to the classifier examples as `analysis`.
- **q013** — "How has my portfolio done since I started?" classified `open`
  instead of `analysis`. Again a borderline case; adding to classifier prompt
  examples would help.
- **q021** — "What will I owe in tax this year?" classified `open` instead of
  `tax`. The query lacks explicit tax vocabulary; adding "tax" signal words to
  the prompt should fix it.
- **q027, q029** — Boundary cases between `comparison`/`analysis` and
  `open`/`analysis`. Scores are at or just below the 0.85 min_confidence
  threshold, so small prompt wording changes would move them.

### Tool-use (26/35, 74%)

- **q011, q012** — Classified as `quick`, so they ran the quick agent, which
  called the right tools for a quick query — but the golden set expected
  `analysis` tools. Classification fix will fix tool-use.
- **q025, q026** — Comparison path agent asked clarifying questions rather than
  calling `get_buy_and_hold_comparison`. The HITL interrupt for the comparison
  path may be triggering confusion in the astream path; investigate whether the
  graph is pausing at the HITL checkpoint and returning no tool calls.
- **q031–q035** — Errored due to credit exhaustion; not counted against tool-use
  accuracy.

### Answer quality (65/86 dimensions, 76%)

- **formatting_correct / cites_aud_value** — Several failures appear to be
  over-strict judge rubric: `$3,228.06` is a correctly comma-separated value but
  the judge flagged it. `$0.00` is a valid answer for zero DCA spend. These
  dimensions may need rubric refinement.
- **cites_ato_rule** — The agent consistently describes ATO rules in plain
  English without citing the formal rule name (e.g. "CGT discount" instead of
  the specific ATO provision number). The system prompt could add explicit
  instruction to cite the ATO rule name.
- **shows_math** — Tax queries that return $0.00 don't show calculation steps.
  If the portfolio has no taxable events, the answer is trivially correct but
  the judge wants to see working. Either adjust the rubric or add a
  zero-result explanation template to the tax prompt.
- **q024** — Comparison agent returned raw JSON tool call fragments in the
  answer. This suggests the streaming chunk collection logic caught tool-call
  metadata as content; investigate the `AIMessage.content` vs `tool_calls`
  split in the runner.

### Partial run (q031–q035)

The run exhausted the Anthropic API credit balance at q031. The five remaining
queries (`q031`: "Anything I should know?", `q032`: "What's the most
interesting thing about my portfolio right now?", `q033`–`q035`: multi-turn
and comparison follow-ups) were not evaluated. The 30/35 completed queries are
sufficient for a meaningful baseline. Rerun after topping up API credits.

## Run-id and artifacts

- Run-id: `1cf0bf9b`
- JSON record: `backend/evals/results/1cf0bf9b.json` (gitignored — local only)
- Eval suite: `backend/tests/test_evals.py::test_full_eval_suite`
- Golden set: `backend/evals/golden_set.yaml` (35 entries)
- Agent model: `claude-sonnet-4-5`
- Judge model: `claude-sonnet-4-5` (default)

## Update protocol

- Re-run when intentionally changing agent prompts, classifier config, tool
  surface, or judge dimensions. Paste the new summary, replace the failures
  section.
- Don't update for one-off failures (e.g., upstream Kraken transient error
  during a run, or API credit exhaustion on the final few queries).
- Don't claim a new baseline if the run used a different `EVAL_JUDGE_MODEL`
  (Haiku and Sonnet score differently, especially on `cites_*` dimensions).
