# Dosing

The work done before the page opens has a ceiling. It does not grow with the size of the PR.

## Read first

- `walkthrough summary RUN_DIR`: files, changed functions with their signals, suggested parts, entry points, hunks, commits, glossary and the PR description.
- The glossary files it lists, at the branch's version.
- Code you need, with Read, under `meta.root` from `index.json`.

## Choose the skeleton

The skeleton is the set of changed functions that tells the story. At most 12, or the `--max-skeleton` the user asked for.

- **Small PR:** every changed function fits in the skeleton. Put them all there, and plan `short` explanations for their direct neighbors and for the tests that call them.
- **Large PR:** pick by these signals, in order:
  1. it sits on the path from an entry point through other changes (`reaches entry` is yes);
  2. many other changes link to it (`linked changes`);
  3. it is a new building block other changes use;
  4. many lines changed.
- Tests, renames and one-line wiring stay out of the skeleton. They go to `other`.
- Every changed function lands in exactly one place: `skeleton`, `other`, or a file in `mechanical.paths`.

## Mechanical changes

Files changed only by renames, import moves, formatting or generation go to `mechanical.paths`, with one sentence in `mechanical.summary`.

## Parts and reading order

- Start from the suggested parts. Merge or split them by meaning.
- Name each part with a short noun phrase in the conversation language.
- Order each part's `roteiro` from the entry point down, following the flow of execution.
- The roteiros together list exactly the skeleton.

## plan.json

```json
{"parts": [{"title": "Desconto no preço", "roteiro": ["app/pricing.py#base_price", "app/pricing.py#discount"]}],
 "skeleton": ["app/pricing.py#base_price", "app/pricing.py#discount"],
 "other": ["tests/test_pricing.py#test_base_price"],
 "mechanical": {"summary": "Três arquivos só reorganizaram imports.", "paths": ["app/a.py", "app/b.py", "app/c.py"]}}
```

## The story

Write `overview.story` after the plan: two to five short paragraphs, from the context to the problem to what the branch does. Use `[[name]]` markers for the functions it mentions. List each glossary and code divergence in `overview.glossaryDivergences`, one sentence each.
