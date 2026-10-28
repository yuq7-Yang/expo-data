# Baseline observations

The clean baseline was run without the skill. The agent already understood most
general data-governance practices, but left three material loopholes.

- Run date: 2026-10-28 (Asia/Shanghai)
- Harness: fresh isolated Codex subagent, inherited model preset
- Inputs exposed: `evals/scenarios.md` only

1. It allowed a privacy exception: "Phone numbers are excluded unless they are
   clearly published business-contact numbers and the search use is approved."
   For a public expo assistant, the safer invariant is that phone numbers and
   personal fields remain outside retrieval; a separately authorized contact
   product is a different data product.
2. It proposed: "ambiguous new rows may publish with provisional new IDs and a
   review flag." Provisional IDs can escape into URLs, analytics, caches, and
   integrations. Unresolved identity must not enter the stable registry.
3. It proposed a "targeted index update" after a correction. Scoped rebuilds are
   acceptable only when the pipeline proves dependency coverage, regenerates the
   release manifest, runs the same gates, and verifies deterministic output.

The skill therefore focuses on these non-obvious boundaries rather than
repeating generic ETL advice.
