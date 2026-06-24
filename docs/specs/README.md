# Specification

The product specification set for Sculptor — long-lived, maintained documents describing what the
product is, the contracts it upholds, and how its behavior is verified.

- **[SPEC.md](SPEC.md)** — the narrative product specification: what Sculptor is and how each feature
  behaves, in prose (Overview, Scenarios, System Components, Domain Model, the feature-by-feature
  Details, the `sculpt` CLI, non-functional behavior, the engineering substrate, and build/release).
- **[requirements.md](requirements.md)** — the measurable and contractual facts the prose
  deliberately leaves out: numeric targets, version/platform bars, persistence and migration
  guarantees, integration contracts, and the open questions where the product pins no value yet.
- **[scenarios.md](scenarios.md)** — every user-facing interaction expressed as a Given/When/Then
  scenario, the UI-level acceptance layer.
- **[scenario_coverage.md](scenario_coverage.md)** — maps each scenario to the integration test that
  demonstrates it (coverage and traceability).

## How they relate

`SPEC.md` is the source of truth for behavior; `requirements.md` pins the measurable targets and
contracts that behavior rests on; `scenarios.md` turns the behavior into concrete acceptance checks;
and `scenario_coverage.md` measures how well those checks are demonstrated by automated tests.

| Document | Answers | Layer |
|---|---|---|
| `SPEC.md` | What is the product, and how does each feature behave? | Functional behavior, in prose |
| `requirements.md` | What measurable targets, limits, and contracts does the product meet? | Requirements |
| `scenarios.md` | What exactly happens on screen, action by action? | UI-level acceptance |
| `scenario_coverage.md` | Which test demonstrates each scenario? | Coverage / traceability |
