# Explanation format

These explanations sit next to the code in a page a reviewer navigates like vim. The reviewer reads the code beside them. The explanation says what the code alone does not: what the function is for, and how this branch changes what it does. Depth comes later, when the reviewer opens a folded section or asks a question.

## Language

Write in the language the task names. Keep identifiers as they are in the code.

## Shape

Every entry is JSON:

```json
{"level": "full", "summary": "One sentence that starts with a verb.", "sections": {"change": "..."}}
```

The page always shows `summary` and the core section. Every other section starts folded.

| level | when | core section | optional sections |
|---|---|---|---|
| `full` | skeleton, or Explain | `change` for a changed function, `relation` for an unchanged one | `steps`, `why`, `risk`, `syntax` |
| `short` | neighbors and tests in a small PR | same as `full` | none |
| `summary` | every other changed function, and hunks | none | none |

What each field holds, with its word limit. `walkthrough validate` rejects anything longer. Line markers do not count as words.

- `summary` (25 words): what the function does, as it is now.
- `change` (60 words): how this branch changes what the function does. For a modified function, say what it did and what it does now. For an added function, say what it adds to the flow.
- `relation` (40 words): how this unchanged function connects to the change.
- `steps` (at most 6 steps, 25 words each): a numbered list of the parts that matter for the change. Each step ends with the line marker of the lines it covers. Skip the obvious.
- `why` (50 words): the reason, from the PR, the commits or the code. Write it only when one is recorded. Never guess.
- `risk` (50 words): a concrete risk the code shows, such as a caller that breaks or a case left out. Write it only when there is one. The page shows it unfolded.
- `syntax` (60 words): constructs a newcomer to the language would trip on, one line each with a line marker.

Write an optional section only when it tells the reader something the code beside it does not show. An explanation with only `summary` and `change` is often the best one.

## Markers

- `[[L12]]` or `[[L12-15]]` points at lines of the function being explained. Stay inside its line range.
- `[[name]]` points at another function. Use only functions that `walkthrough context` lists, or that the index has. When the name repeats in several files, use the full id, `[[path/to/file.py#name]]`.
- No other links, no HTML, no headings inside sections. Plain Markdown paragraphs, lists, `code` and **bold**.

## How to write

- Short sentences, one idea each, plain words. No em dashes.
- Say intent and effect. Never restate the code line by line.
- Define a domain term only when the sentence needs it, in a few words.
- The code is the source of truth. A glossary, read at the branch's version, gives the terms. When glossary and code disagree, follow the code. The disagreement goes in the overview's `glossaryDivergences`, not in each function.

## Example

```json
{"level": "full", "summary": "Calcula o preço final de um item.", "sections": {
  "change": "Antes multiplicava o valor pela taxa e parava aí. Agora subtrai o desconto de [[discount]], então [[describe]] passa a devolver o preço menor.",
  "steps": "1. Multiplica o valor pela taxa de [[RATE]] [[L11]].\n2. Subtrai o desconto [[L12]].",
  "risk": "Quem guardava o preço sem desconto, como o relatório mensal, vai ver números menores."}}
```
