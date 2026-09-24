# Interview demo script

Use a clean default workspace for genuine manual review. The bundled sample report is a labeled simulation, not an actual model result.

## Open with the problem

“This is not a SQL chatbot. It is the infrastructure behind a small human-expertise-to-model-evaluation loop. The key question is whether a correction becomes reliable, reusable data and whether the improvement survives a held-out test.”

## Show a specific failure

Open **Human review** and select the `dev_monthly_revenue` seed. The original scripted answer joins orders to order items and sums the order-level total, repeating that total for each item. Show the expected and actual tables on more than one fixture.

Be explicit: “This initial answer is an intentionally faulty demonstration query. In a live development run, this panel instead uses a stored model baseline output.”

## Make a review real

Read the question and business rules. Remove the unnecessary item join, or use the reference as a starting point and inspect it. Add your own reviewer name and a short explanation. Click **Validate on 3 fixtures**, then **Approve correction**. Show the retained reference, corrected SQL, and append-only revision history.

Explain why “query executed” is not the same as “query was correct.” Also explain why matching a finite fixture suite does not prove universal SQL equivalence.

## Exercise the data pipeline

Generate variants. Show 48 additional tasks, deterministic parent IDs, generator metadata, and pending—not inherited approved—status. Generate again and show duplicate suppression. Export approved data and point out that the holdout never appears in it.

The generator is template-based, not an unconstrained LLM. Explain that this intentionally trades linguistic variety for traceable reference answers in the MVP.

## Exercise evaluation

Approve examples from several categories, then create an experiment. Use **scripted demo** for the offline demo; it consumes no real tokens and does not prove model improvement. For genuine evidence, configure a live model and report its actual results.

Show fixed example selection, immutable dataset/prompt hashes, paired per-task outcomes, and the family-cluster confidence interval. Show a remaining failure, not only a green headline. Pause and resume a run, explaining the distinction between exactly-once stored results and potentially repeated external API calls after a crash.

## Explain the next increment

“I would collect independent expert reviews, design a new final test set, measure a live baseline and few-shot arm, and only then consider fine-tuning. For a public deployment I would move execution into independently isolated workers and add identity, tenancy, leases, and operational monitoring.”

## Resume wording after genuine completion

“Built a human-in-the-loop SQL data and evaluation workbench with fixture-based correctness checks, auditable review revisions, approved-only dataset exports, resumable paired evaluations, and family-cluster bootstrap reporting.”

Add model-performance percentages only after measuring a real model. Never reuse the sample simulation percentages as a resume result.
