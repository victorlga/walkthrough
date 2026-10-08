import copy
import unittest

import helpers  # noqa: F401
from walkthrough.explanations import merge
from walkthrough.validate import prune, validate


def node(name, lines, status, path):
    return {"name": name, "qualname": name, "lines": lines, "change": {"status": status}, "path": path}


INDEX = {
    "nodes": {
        "a.py#calc": node("calc", [10, 20], "modified", "a.py"),
        "a.py#new_fn": node("new_fn", [30, 35], "added", "a.py"),
        "a.py#handler": node("handler", [40, 45], "unchanged", "a.py"),
        "b.py#handler": node("handler", [1, 5], "unchanged", "b.py"),
        "c.clj#source-amount->spread": node("source-amount->spread", [1, 9], "modified", "c.clj"),
        "gen/d.py#gen": node("gen", [1, 3], "modified", "gen/d.py"),
    },
    "changed": ["a.py#calc", "a.py#new_fn", "c.clj#source-amount->spread", "gen/d.py#gen"],
    "hunks": [{"id": "README.md@3", "path": "README.md", "lines": []}],
}

PLAN = {
    "parts": [{"title": "cálculo", "roteiro": ["a.py#calc", "a.py#new_fn"]}],
    "skeleton": ["a.py#calc", "a.py#new_fn"],
    "other": ["c.clj#source-amount->spread"],
    "mechanical": {"summary": "Código gerado.", "paths": ["gen/d.py"]},
}

FULL_MODIFIED = {"level": "full", "summary": "Calcula o total.", "sections": {
    "change": "Somava tudo. Agora aplica [[new_fn]] antes de somar, e [[source-amount->spread]] recebe o valor menor.",
    "steps": "1. Lê a taxa [[L11]].\n2. Aplica [[new_fn]] [[L12-14]].", "why": "Faltava o desconto.",
    "risk": "Quem guardava o total antigo vê outro número."}}

EXPLANATIONS = {
    "overview": {"story": "A branch passa a aplicar [[calc]] com desconto.", "glossaryDivergences": []},
    "nodes": {
        "a.py#calc": FULL_MODIFIED,
        "a.py#new_fn": {"level": "full", "summary": "Calcula o desconto.", "sections": {
            "change": "Nova. Isola o desconto que [[calc]] aplica."}},
        "a.py#handler": {"level": "short", "summary": "Responde a requisição.", "sections": {
            "relation": "Chama [[calc]] e devolve o total."}},
        "c.clj#source-amount->spread": {"level": "summary", "summary": "Passa a usar [[calc]]."},
        "README.md@3": {"level": "summary", "summary": "Documenta o desconto."},
    },
    "pruned": [],
}


class ValidateTest(unittest.TestCase):
    def check(self, explanations=None, plan=None, index=None, max_skeleton=12):
        return [str(p) for p in validate(index or INDEX, plan or PLAN, explanations or EXPLANATIONS, max_skeleton)]

    def changed_copy(self):
        return copy.deepcopy(EXPLANATIONS)

    def test_a_correct_run_has_no_problems(self):
        self.assertEqual(self.check(), [])

    def test_line_marker_outside_the_function(self):
        e = self.changed_copy()
        e["nodes"]["a.py#calc"]["sections"]["steps"] = "1. Fora [[L50]]."
        self.assertEqual(self.check(e), ["a.py#calc [steps] [[L50]] lines 50-50 are outside 10-20"])

    def test_ambiguous_name_lists_the_candidates(self):
        e = self.changed_copy()
        e["nodes"]["a.py#calc"]["sections"]["risk"] = "Chamada por [[handler]]."
        self.assertEqual(self.check(e), ["a.py#calc [risk] [[handler]] is ambiguous: a.py#handler, b.py#handler"])

    def test_an_ambiguous_name_resolves_to_the_function_the_owner_calls(self):
        index = copy.deepcopy(INDEX)
        index["nodes"]["a.py#calc"]["links"] = [{"line": 12, "col": 0, "len": 7, "to": "b.py#handler"}]
        e = self.changed_copy()
        e["nodes"]["a.py#calc"]["sections"]["risk"] = "Usa [[handler]]."
        self.assertEqual(self.check(e, index=index), [])

    def test_an_ambiguous_name_in_the_story_resolves_to_the_changed_one(self):
        index = copy.deepcopy(INDEX)
        index["nodes"]["b.py#calc"] = node("calc", [1, 3], "unchanged", "b.py")
        e = self.changed_copy()
        e["overview"]["story"] = "Muda [[calc]]."
        self.assertEqual(self.check(e, index=index), [])

    def test_unknown_function(self):
        e = self.changed_copy()
        e["overview"]["story"] = "Usa [[nao_existe]]."
        self.assertEqual(self.check(e), ["overview [story] [[nao_existe]] is not a function in the index"])

    def test_line_markers_do_not_belong_in_the_overview(self):
        e = self.changed_copy()
        e["overview"]["story"] = "Veja [[L3]]."
        self.assertEqual(self.check(e), ["overview [story] [[L3]] line markers only work inside a function"])

    def test_a_changed_function_says_how_the_change_alters_it(self):
        e = self.changed_copy()
        del e["nodes"]["a.py#calc"]["sections"]["change"]
        self.assertEqual(self.check(e), ["a.py#calc [sections]  missing section 'change' for a full modified explanation"])

    def test_an_unchanged_function_says_how_it_connects_to_the_change(self):
        e = self.changed_copy()
        e["nodes"]["a.py#handler"]["sections"] = {"change": "Nada mudou."}
        self.assertEqual(self.check(e), ["a.py#handler [sections]  missing section 'relation' for a short unchanged explanation",
                                         "a.py#handler [sections] change is not allowed for a short unchanged explanation"])

    def test_short_explanations_hold_only_the_core(self):
        e = self.changed_copy()
        e["nodes"]["a.py#handler"]["sections"]["steps"] = "1. Lê [[L41]]."
        self.assertEqual(self.check(e), ["a.py#handler [sections] steps is not allowed for a short unchanged explanation"])

    def test_a_summary_is_one_sentence_and_nothing_else(self):
        e = self.changed_copy()
        e["nodes"]["c.clj#source-amount->spread"]["sections"] = {"change": "Passa a usar [[calc]]."}
        self.assertEqual(self.check(e), ["c.clj#source-amount->spread [sections] change is not allowed for a summary modified explanation"])

    def test_the_long_sections_of_earlier_versions_are_unknown(self):
        e = self.changed_copy()
        e["nodes"]["a.py#calc"]["sections"]["context"] = "Usada pela API."
        self.assertEqual(self.check(e), ["a.py#calc [sections] context is not a known section"])

    def test_the_change_fits_a_quick_read(self):
        e = self.changed_copy()
        e["nodes"]["a.py#calc"]["sections"]["change"] = " ".join(["palavra"] * 61)
        self.assertEqual(self.check(e), ["a.py#calc [change]  has 61 words, the limit is 60"])

    def test_line_markers_do_not_count_as_words(self):
        e = self.changed_copy()
        e["nodes"]["a.py#calc"]["summary"] = " ".join(["palavra"] * 25) + " [[L11]]"
        self.assertEqual(self.check(e), [])

    def test_steps_stay_few_and_short(self):
        e = self.changed_copy()
        steps = "\n".join(f"{n}. Faz [[L11]]." for n in range(1, 8))
        e["nodes"]["a.py#calc"]["sections"]["steps"] = steps + "\n8. " + " ".join(["longo"] * 25) + " [[L12]]."
        self.assertEqual(self.check(e), ["a.py#calc [steps]  has 8 steps, the limit is 6",
                                         "a.py#calc [steps] 8. has 26 words, the limit is 25"])

    def test_the_story_stays_short(self):
        e = self.changed_copy()
        e["overview"]["story"] = "Muda [[calc]]. " + " ".join(["palavra"] * 130)
        self.assertEqual(self.check(e), ["overview [story]  has 132 words, the limit is 130"])

    def test_every_step_needs_a_line_marker(self):
        e = self.changed_copy()
        e["nodes"]["a.py#calc"]["sections"]["steps"] = "1. Lê a taxa [[L11]].\n2. Soma."
        self.assertEqual(self.check(e), ["a.py#calc [steps] 2. Soma. step without a line marker"])

    def test_every_changed_function_is_in_the_plan(self):
        plan = copy.deepcopy(PLAN)
        plan["other"] = []
        self.assertIn("plan [coverage] c.clj#source-amount->spread changed function is not in the plan", self.check(plan=plan))

    def test_skeleton_has_a_ceiling(self):
        self.assertEqual(self.check(max_skeleton=1), ["plan [skeleton]  has 2 functions, the maximum is 1"])

    def test_docs_only_branch_validates_with_an_empty_plan(self):
        index = {"nodes": {}, "changed": [], "hunks": [{"id": "README.md@3", "path": "README.md", "lines": []}]}
        plan = {"parts": [], "skeleton": [], "other": [], "mechanical": {"summary": "", "paths": []}}
        explanations = {"overview": {"story": "Só a documentação mudou.", "glossaryDivergences": []}, "nodes": {}, "pruned": []}
        self.assertEqual(self.check(explanations, plan, index), [])

    def test_prune_removes_a_broken_explanation_and_records_why(self):
        e = self.changed_copy()
        e["nodes"]["c.clj#source-amount->spread"]["summary"] = "Usa [[handler]]."
        remaining = prune(e, validate(INDEX, PLAN, e))
        self.assertEqual(remaining, [])
        self.assertNotIn("c.clj#source-amount->spread", e["nodes"])
        self.assertEqual(e["pruned"][0]["id"], "c.clj#source-amount->spread")
        self.assertEqual(self.check(e), [])

    def test_merge_replaces_nodes_and_keeps_the_rest(self):
        merged = merge(self.changed_copy(), {"nodes": {"a.py#new_fn": {"level": "summary", "summary": "Outra."}}})
        self.assertEqual(merged["nodes"]["a.py#new_fn"]["summary"], "Outra.")
        self.assertIn("a.py#calc", merged["nodes"])


if __name__ == "__main__":
    unittest.main()
