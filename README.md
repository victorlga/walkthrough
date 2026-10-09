# walkthrough

An agent skill that turns a branch or a PR into a page you navigate like go-to-definition in vim. Click into a function, back out along the same path, and read a short AI explanation next to the code at every step.

It follows the `SKILL.md` format, so any coding agent that reads skills can run it.

## What the page gives you

- The story of the change and a reading route through the functions that matter.
- For each function, what it does and how the change alters it. Steps, the reason and the risks stay folded until you open them.
- The code with the diff inline, folding like an editor, opened at the first change.
- Callers, callees and tests one click away.
- On a PR, line comments and a verdict that your agent posts as one GitHub review.
- When the page is published to a host with an in-page model, an Explain button and a question box under each function.

Large PRs are dosed. At most 12 functions get a full explanation, and every other change gets one line.

## Languages

| Language | Language server |
|---|---|
| Python | basedpyright |
| TypeScript and JavaScript | TypeScript 7 (`tsc --lsp`) |
| Clojure | clojure-lsp |

Next: Java, Rust and Go.

## Install

Clone the repo into the folder where your agent loads skills, or point your agent at `SKILL.md`.

```bash
git clone https://github.com/victorlga/walkthrough
```

It needs git, Python 3 and, for PRs, the GitHub CLI. `scripts/walkthrough doctor` lists any missing language server with its install command.

## Use

Ask your agent for a walkthrough: "walkthrough this branch" or "walkthrough PR 123".

On the page, `n` goes to the next step of the route, Backspace or Ctrl-O goes back, and `e` asks for an explanation.

## How it works

1. `scripts/walkthrough index` asks the language server for symbols, definitions and callers, and writes an index of the changed functions and the code around them.
2. The agent picks the route and writes the explanations, in parallel when it can run subagents.
3. `validate` checks every reference against the index, along with the word limits.
4. `render` builds one HTML file that opens in any browser.
5. On a PR, the Review panel copies your comments and verdict as a block. Paste it into the agent, and `scripts/walkthrough review` posts it with the GitHub CLI.

The skill only reads your repo, and posts nothing except a review you paste back. A PR or another branch is checked out in a temporary worktree under `~/.cache/walkthrough`, removed at the end.

## Tests

```bash
python3 -m unittest discover -s tests
node --test tests/page-core.test.js
```

The index tests start the real language servers.
