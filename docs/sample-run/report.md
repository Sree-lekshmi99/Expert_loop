# ExpertLoop experiment: Scripted end-to-end example

**Scripted simulation; not model evidence**

Generated: 2026-09-23T23:12:34.653+00:00
Run: `run_1a2d8d6cd5` · Status: **completed**

## Configuration

Provider: demo
Requested model: `scripted-demo-v1`
Split: holdout
Fixed approved development examples: 6
Dataset hash: `f27100e8b252a7c920ab0bdd40b1ed02202276d884b644430f316e2658bb4d5f`
Example hash: `e6e2c02e175b8bd8fd7d03907f2289f1fe436c4b6bf3b67dadab118232b4730c`
Prompt version: `sql-assistant-v1`
Evaluator: `sqlite-suite-v1`

## Paired results

Completed pairs: 30/30; template families: 10
Baseline execution accuracy: 23.3%
Approved-example execution accuracy: 86.7%
Difference: +63.3 percentage points
95% family-cluster paired-bootstrap interval: [+43.3, +83.3] percentage points
Wins / regressions / unchanged: 19 / 0 / 11

| Category | Paired tasks | Baseline | Approved examples |
|---|---:|---:|---:|
| Aggregation | 6 | 50.0% | 100.0% |
| Business rules | 3 | 0.0% | 100.0% |
| Date boundaries | 6 | 16.7% | 83.3% |
| Join cardinality | 6 | 16.7% | 100.0% |
| Missing values | 6 | 33.3% | 83.3% |
| Ranking & ties | 3 | 0.0% | 33.3% |

## Usage and latency

Attempted requests (including retries): 60 / 240
These are scripted calls, with no tokens or model latency, in demo mode.
- baseline: {'median_latency_ms': None, 'p95_latency_ms': None, 'input_tokens': 0, 'output_tokens': 0, 'provider_errors': 0}
- improved: {'median_latency_ms': None, 'p95_latency_ms': None, 'input_tokens': 0, 'output_tokens': 0, 'provider_errors': 0}

## Interpretation and limitations

A task passes only if its result matches the reference on all three fixtures. Aliases are ignored; column position, duplicates, NULLs and task-specified row order matter.
The bootstrap resamples template families and retains paired baseline/improved results. It uses 5,000 replicates and seed 7. With only ten holdout families, uncertainty estimates are preliminary.
Repeated holdout use can contaminate future decisions. Freeze this test set before model/prompt selection and create a fresh independent test set for final claims.
Templates, questions and fixtures are synthetic and are not independently domain-expert-certified. Passing fixtures does not prove SQL equivalence on every possible database.
Partial reports use completed pairs only and must not be compared as final experiment results.
The approved-example arm is few-shot prompting, not parameter training. No fine-tuning is included.
Development runs exclude exact few-shot tasks but may contain related template siblings. They are diagnostics, not generalization evidence.
A local single-user service is not a production multi-tenant deployment. See docs/SECURITY.md.
