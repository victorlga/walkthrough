import unittest

import helpers  # noqa: F401
from walkthrough.graph import entry_points, impact_paths, parts, signals


def node(callers=(), links=(), status="unchanged", test=False, added=(), removed=()):
    return {"callers": [{"from": c, "lines": [], "test": c.startswith("test")} for c in callers],
            "callersComputed": True, "links": [{"to": t} for t in links], "test": test,
            "change": {"status": status, "added": list(added), "removed": list(removed)}}


class GraphTest(unittest.TestCase):
    def setUp(self):
        self.nodes = {
            "handler": node(),
            "describe": node(callers=["handler"], links=["base_price"]),
            "base_price": node(callers=["describe", "test_bp"], links=["discount"], status="modified",
                               added=[7, 8], removed=[{"after": 6, "text": ["old"]}]),
            "discount": node(callers=["base_price"], status="added", added=[3, 4]),
            "test_bp": node(links=["base_price"], test=True),
            "parent": node(links=["a2", "b2"]),
            "a2": node(callers=["parent"], status="modified", added=[1]),
            "b2": node(callers=["parent"], status="modified", added=[1]),
            "lonely": node(status="modified", added=[1]),
        }
        self.changed = ["base_price", "discount", "a2", "b2", "lonely"]

    def test_entry_points_are_upward_nodes_nobody_calls_with_tests_apart(self):
        upward = {"base_price", "discount", "describe", "handler", "test_bp"}
        self.assertEqual(entry_points(self.nodes, upward), (["handler"], ["test_bp"]))

    def test_impact_is_the_shortest_path_from_each_change_to_each_entry(self):
        impact = impact_paths(self.changed, self.nodes, {"handler"})
        self.assertEqual(impact["base_price"], {"paths": [["base_price", "describe", "handler"]], "omitted": 0})
        self.assertEqual(impact["discount"]["paths"], [["discount", "base_price", "describe", "handler"]])
        self.assertEqual(impact["lonely"], {"paths": [], "omitted": 0})

    def test_impact_keeps_ten_paths_and_counts_the_rest(self):
        nodes = {"changed": node(callers=[f"route{n:02d}" for n in range(12)], status="modified")}
        for n in range(12):
            nodes[f"route{n:02d}"] = node()
        impact = impact_paths(["changed"], nodes, {f"route{n:02d}" for n in range(12)})
        self.assertEqual(len(impact["changed"]["paths"]), 10)
        self.assertEqual(impact["changed"]["omitted"], 2)

    def test_parts_join_direct_calls_and_siblings_under_one_caller(self):
        self.assertEqual(parts(self.changed, self.nodes), [["base_price", "discount"], ["a2", "b2"], ["lonely"]])

    def test_signals_describe_each_change(self):
        impact = impact_paths(self.changed, self.nodes, {"handler"})
        result = signals(self.changed, self.nodes, impact)
        self.assertEqual(result["base_price"], {"linesChanged": 3, "new": False, "linkedChanges": 1, "onEntryPath": True})
        self.assertEqual(result["discount"]["new"], True)
        self.assertEqual(result["lonely"]["onEntryPath"], False)


if __name__ == "__main__":
    unittest.main()
