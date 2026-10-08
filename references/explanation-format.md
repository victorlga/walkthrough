# Explanation format

These explanations sit next to the code in a page a reviewer navigates like vim. They exist so the reviewer understands what changed, why, and what it touches, without reading every line first.

## Language

Write in the language the task names. Keep identifiers as they are in the code.

## Shape

Every entry is JSON:

```json
{"level": "full", "summary": "One sentence that starts with a verb.", "sections": {"context": "...", "steps": "..."}}
```

| level | when | sections |
|---|---|---|
| `full`, function added | skeleton, or Explain | `context`, `why`, `steps`, `impact` |
| `full`, function modified | skeleton, or Explain | `context`, `before`, `why`, `steps`, `impact` |
| `full`, function unchanged | Explain on a neighbor | `context`, `steps`, `relation` |
| `short` | neighbors and tests in a small PR | `context`, `relation` |
| `summary` | every other changed function, and hunks | none |

`syntax` is optional on any level with sections.

What each section holds:

- `context`: what this function is for in the system, in one to three sentences. Define each domain term the first time it appears.
- `before`: what it did before this branch, in one or two sentences.
- `why`: why it changed, or why it exists. If the PR, the commits and the code do not say, write that the reason is not recorded. Never guess.
- `steps`: a numbered list. Each step says what happens and why it matters, and ends with the line marker of the lines it explains.
- `impact`: who calls it and what changes for them. Name a concrete risk only when the code shows one.
- `relation`: how this function connects to the change being reviewed.
- `syntax`: language constructs a newcomer to this language would trip on, such as threading macros, destructuring or decorators. One line each, with a line marker.

## Markers

- `[[L12]]` or `[[L12-15]]` points at lines of the function being explained. Stay inside its line range.
- `[[name]]` points at another function. Use only functions that `walkthrough context` lists, or that the index has. When the name repeats in several files, use the full id, `[[path/to/file.py#name]]`.
- No other links, no HTML, no headings inside sections. Plain Markdown paragraphs, lists, `code` and **bold**.

## How to write

- Go from the base to the concrete: the context, then the problem, then the code.
- Short sentences, one idea each, plain words. No em dashes.
- Explain intent and effect. Do not restate the code line by line.
- The code is the source of truth. A glossary, read at the branch's version, gives the terms. When glossary and code disagree, follow the code and say what differs.

## Example

```json
{"level": "full", "summary": "Calcula o preço já com o desconto.", "sections": {
  "context": "É chamada por [[describe]], que monta a resposta da API de preços.",
  "before": "Multiplicava o valor pela taxa e parava aí.",
  "why": "O motivo não está registrado no PR nem nos commits.",
  "steps": "1. Multiplica o valor pela taxa, que vem de [[RATE]] [[L11]].\n2. Subtrai o desconto calculado por [[discount]] [[L12]].",
  "impact": "[[describe]] e o handler acima dela passam a devolver o preço menor."}}
```
