# Architecture and design decisions

## Scope

ExpertLoop is a local, single-user portfolio MVP. It captures a SQL correction, verifies it against three deterministic databases, retains review provenance, exports approved development examples, and compares baseline versus few-shot prompting. It does not train model weights.

The initial suggestion used DuckDB and Streamlit. This implementation deliberately uses SQLite and a bundled browser UI: one Python service, no frontend build, no database installation, and a built-in SQL authorizer. This is a scope reduction, not a claim that SQLite is the right production warehouse.

## Components

```text
Browser: plain HTML / CSS / JavaScript
  └─ FastAPI
      ├─ SQLite metadata (WAL + short transactions)
      │   ├─ tasks + current review state
      │   ├─ append-only review events
      │   ├─ generation batches
      │   ├─ immutable experiment snapshots
      │   └─ unique (run, task, arm) results
      ├─ Template generator
      │   └─ three mechanically checked fixture outputs
      └─ Evaluation coordinator: one active run, 1–4 concurrent calls
          ├─ Scripted demo provider OR OpenAI Responses adapter
          ├─ isolated-configuration SQL worker subprocess
          └─ paired, family-cluster bootstrap report
```

## Data contract

The four fixture tables are `customers`, `orders`, `order_items`, and `products`. Money is integer USD cents. Dates are ISO calendar dates. Revenue includes completed orders only unless the question explicitly asks for cancelled purchases. Order totals equal their item totals; multiplying the order total through a one-to-many join is incorrect.

Three fixtures (`standard`, `edge_cases`, `sparse`) differ in transactions and quantities. They include guest customer IDs, NULL countries, customers with no purchases, unsold products, cancellations, zero prices, repeated values, and interval boundaries. Fixtures are constructed from fixed seeds and hashed in each experiment.

The catalog starts with 12 development seed tasks and 30 holdout tasks. The latter use 10 distinct template families with 3 interval variants each. Generation adds 48 variants to the development families, for 60 development tasks total. Holdout templates are never generator inputs. All reference SQL is code-authored/template-derived; no independent human-domain-expert certification is implied.

The holdout is family-disjoint by declared catalog IDs and contains no exact reference-SQL duplicates with development. Related concepts and schema are intentionally shared. Family separation is a useful software guard, not proof of semantic or distributional independence. The benchmark is too small and synthetic to stand in for an independent professional evaluation.

## Review and generation

A review names a reviewer, records a reason, and uses an optimistic revision check. Approval requires a successful fresh validation on every fixture. Reference SQL is immutable in the UI; corrections are stored separately. A reviewer who believes the reference itself is wrong should reject the task and fix/version the source catalog, not coerce a correction through an incorrect oracle.

Synthetic generation is deterministic template expansion, **not LLM-based synthesis**. IDs depend on the template and parameters, so repeated generation is idempotent. Parent task IDs and generator version are retained. New variants never inherit their parent's approved state. This prioritizes a trustworthy mechanical oracle over unconstrained generation.

The explicit `demo` CLI uses an automation actor named `SCRIPTED_DEMO_NOT_HUMAN` to exercise approval mechanics. Its isolated state and exports must not be represented as real expert review. The normal app starts with zero approvals.

## Experiment design

Baseline receives schema, rules, and the question. The improved arm receives the same plus a fixed, category-diverse selection of approved development examples. Selection is independent of each holdout question. The live provider function accepts a question string and approved examples, not a task containing a reference answer. Neither the holdout oracle nor its category/ID is serialized to the provider.

The snapshot freezes tasks, expected outputs, approved-example revisions, model configuration, the full system prompt, evaluator version, fixture hashes, and prompt hashes. Baseline/improved scheduling alternates per-task order. Inference is single-sample per task/arm. There is no model-weight update and no claim that few-shot prompting must improve results.

Development diagnostics exclude the exact selected example tasks. Other members of those development families may remain; development results are therefore in-distribution diagnostics, not generalization evidence.

A task passes only if it matches every fixture. Column aliases are ignored; column positions, duplicates, NULLs, and requested row ordering matter. Numeric comparisons use absolute tolerance 1e-6 and relative tolerance 1e-9. Correctness is evaluated on outputs, not query-string similarity. A finite test suite cannot prove SQL equivalence on every possible database.

## Statistics

Only completed task pairs enter the paired summary. API failures are persisted as failed outputs, so execution accuracy measures the entire answering pipeline; this can include availability failures, not just reasoning errors.

Resample template families with replacement and retain all paired deltas within each sampled family. Report the task-weighted accuracy difference, percentile 95% interval, wins, regressions, and category breakdown. The bootstrap uses 5,000 replicates and seed 7. There are only 10 holdout families, so the interval is preliminary. It does not capture all model-sampling variability, prompt-selection effects, or domain uncertainty. No significance or causal-learning claim is made.

## Recovery and request accounting

Results are unique by `(run_id, task_id, arm)` and written as each task finishes. On process startup, interrupted queued/running runs become paused. Resume skips committed outputs. A transactionally updated request counter reserves every provider attempt, including retries, before dispatch. Bounded retries apply to transport failures, HTTP 429, and server errors. Invalid model access is not retried as if it were a transient failure.

Pause prevents additional queued calls from starting, but in-flight calls can complete. Request caps and per-call output limits are not exact token or dollar budgets. The prompt has no dollar-pricing assumptions. An interrupted or timed-out provider call may still be billed without a returned usage record.

Exactly-once external inference is **not** promised: a process can die after a provider call succeeds but before its result commits. Resume may repeat that call. An exhausted request cap remains exhausted after restart until the user explicitly adds an allowance.

## Deliberate production omissions

There is no distributed queue, worker lease protocol, authentication, tenancy, large-object storage, dataset registry service, secrets manager, independently isolated sandbox fleet, rate limiting across users, fine-tuning job controller, or deployment monitoring. The local app should not be advertised as production-scale infrastructure. A defensible interview discussion explains how these boundaries would change at larger scale.
