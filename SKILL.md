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

## 5. Explain in parallel

Dispatch subagents in one message, so they run at once:

- one per skeleton function, level `full`;
- batches of about 40 for the `summary` of every function in `other` and of every hunk, with the ids in a file, one per line. One line per function is cheap, so these batches may run on a faster model;
- in a small PR, batches of about ten for `short` explanations of direct neighbors and tests.

Give each subagent this prompt, filled in:

```
Write walkthrough explanations for: <ids, or "every id listed in <file>">, level <level>, in <language>.
For each id, run `<W> context <RUN_DIR> '<id>'` (quoted: ids can hold parentheses) and read <skill dir>/references/explanation-format.md.
Ids with "@" are hunks outside any function. Their summaries have no line markers.
You may read files under <meta.root> and run git log there. Glossary: <glossary paths>.
Write {"nodes": {"<id>": {...}}} to <RUN_DIR>/fragments/<batch>.json. Reply with the path only.
```

Then run `W merge RUN_DIR RUN_DIR/fragments/*.json`.

## 6. Validate

Run `W validate RUN_DIR`. Send each failing id back to a subagent with the exact problem lines, at most two rounds. Then run `W validate RUN_DIR --prune` and tell the user which explanations were removed. A pruned function can still be explained later from the page or the chat.

## 7. Render and publish

With the Artifact tool, render into the session scratchpad and publish:

```bash
W render RUN_DIR --out <scratchpad>/<slug>-walkthrough.html --lang <conversation language code>
```

Publish that file with `icon: "code"`, `capabilities: {"sample": {}}` and a one-sentence `description`. The page already follows the artifact page contract. Re-rendering to the same path in this conversation updates the same link.

Without the Artifact tool, use `--mode local --out RUN_DIR/walkthrough.html` and open the file with `open`.

Report the link, the counts and every warning `render` printed: lost links, pruned explanations, cut functions.

## 8. Clean up

Run `W cleanup RUN_DIR` at the end, also after a failure. It removes the temporary worktree.

## 9. Deepen later

When the user asks to explain a function or a part, dispatch subagents for those ids with level `full`, then merge, validate, render to the same path and republish.

## Rules that are easy to break

- Links come only from the index. Explanations may cite only functions the index has, and the validator rejects the rest. Never hand-edit a link into the page.
- Never invent the reason for a change. "The reason is not recorded" is a correct answer.
- The page calls Claude only when the viewer clicks. Never add timers or automatic calls to the template.
- Never commit, push or comment anywhere. This skill only reads the repo and writes to RUN_DIR and the scratchpad.
- Code is the source of truth over any glossary. Report divergences, do not smooth them over.
