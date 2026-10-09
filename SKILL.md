---
name: walkthrough
description: Guided, navigable walkthrough of a branch or PR. Builds an interactive page where you click into functions like go-to-definition in vim, back out along the same path, and read AI explanations built from context to code at every step. Use when the user wants to understand what a branch or PR changed and the code around it, asks for a walkthrough or explanation of a diff, or needs to review changes an agent made.
---

# walkthrough

`W` below means `scripts/walkthrough` inside this skill's base directory. Call it by that full path.

## 0. Preflight

Run `W doctor [TARGET]`. When a language server is missing, show the install command and ask the user to choose: install it, or continue with `--skip-language <name>`, which indexes those files without links.

## 1. Index

```bash
W index [TARGET] [--base REF]
```

TARGET is empty for the current branch, with uncommitted changes included, a PR number, or a branch name. The first output line is RUN_DIR. Exit 2 means a missing server: go back to preflight. Exit 1 means a git problem or an empty diff: report it and stop.

## 2. Read the change

Run `W summary RUN_DIR`. Read the glossary files it lists. For a PR or another branch, the code lives under `meta.root` in `RUN_DIR/index.json`, a temporary worktree. Read code from there, not from the user's checkout.

## 3. Dose

Follow `references/dosing.md` and write `RUN_DIR/plan.json`.

## 4. Overview

Write `RUN_DIR/fragments/overview.json` as `{"overview": {"story": "...", "glossaryDivergences": []}}`, following `references/explanation-format.md`, then run `W merge RUN_DIR RUN_DIR/fragments/overview.json`.

## 5. Explain

Split the work into these batches:

- one per skeleton function, level `full`;
- batches of about 40 for the `summary` of every function in `other` and of every hunk, with the ids in a file, one per line. One line per function is cheap, so these batches may run on a faster model;
- in a small PR, batches of about ten for `short` explanations of direct neighbors and tests.

If you can run subagents, start one per batch, all at once. Otherwise work through the batches yourself, in the same order. Either way, each batch follows this prompt, filled in:

```
Write walkthrough explanations for: <ids, or "every id listed in <file>">, level <level>, in <language>.
For each id, run `<W> context <RUN_DIR> '<id>'` (quoted: ids can hold parentheses) and read <skill dir>/references/explanation-format.md.
Ids with "@" are hunks outside any function. Their summaries have no line markers.
You may read files under <meta.root> and run git log there. Glossary: <glossary paths>.
Write {"nodes": {"<id>": {...}}} to <RUN_DIR>/fragments/<batch>.json. Reply with the path only.
```

Then run `W merge RUN_DIR RUN_DIR/fragments/*.json`.

## 6. Validate

Run `W validate RUN_DIR`. Fix each failing id against the exact problem lines, yourself or through a subagent, at most two rounds. Then run `W validate RUN_DIR --prune` and tell the user which explanations were removed. A pruned function can still be explained later.

## 7. Render

```bash
W render RUN_DIR --out RUN_DIR/walkthrough.html --lang <conversation language code>
```

Open the file in the user's browser: `open` on macOS, `xdg-open` on Linux, `start` on Windows.

If you can publish HTML pages to a host that gives pages an in-page model through a `sample` capability, render with `--mode artifact` instead and publish the file with that capability declared. The page then adds an Explain button and a question box under each function. It works without them everywhere else.

Report the link, the counts and every warning `render` printed: lost links, pruned explanations, cut functions. Tell the user the keys once: `n` goes to the next step of the roteiro, Backspace or Ctrl-O goes back, `e` asks for an explanation. On a PR, mention the Review button: a click on a line number comments that line.

## 8. Clean up

Run `W cleanup RUN_DIR` at the end, also after a failure. It removes the temporary worktree.

## 9. Deepen later

When the user asks to explain a function or a part, write `full` explanations for those ids as in step 5, then merge, validate and render to the same path.

## 10. Post a review

On a PR the page has a Review panel. The user comments on lines, picks a verdict and copies a block that asks you to post it and holds a JSON with `"walkthroughReview": 1`. When the user pastes that block, save the JSON to a temporary file and run:

```bash
W review FILE --dry-run
W review FILE
```

The dry run prints what goes to GitHub. Comments on lines GitHub cannot anchor move into the review body with their file and line. Then post, and report the link it prints. If `gh` refuses, for example an approval of your own PR, report the error as it came.

## Rules that are easy to break

- Links come only from the index. Explanations may cite only functions the index has, and the validator rejects the rest. Never hand-edit a link into the page.
- Never invent the reason for a change. "The reason is not recorded" is a correct answer.
- The page calls a model only when the viewer clicks. Never add timers or automatic calls to the template.
- Never commit, push or comment on your own. The only thing this skill posts is a review the user built on the page and pasted back.
- Code is the source of truth over any glossary. Report divergences, do not smooth them over.
