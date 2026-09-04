import unittest

from src.utils.assignment_strategy import (
    TalkoBaseAssignmentStrategy,
    TalkoEvenDistributionAssignment,
    TalkoRoundRobinAssignment,
)


class TestAssignmentStrategies(unittest.TestCase):
    def test_round_robin_assignment(self):
        items = ["item1", "item2", "item3", "item4", "item5"]
        groups = ["groupA", "groupB"]
        strategy = TalkoRoundRobinAssignment[str]()
        result = strategy.assign(items, groups)

        expected = {
            "item1": "groupA",
            "item2": "groupB",
            "item3": "groupA",
            "item4": "groupB",
            "item5": "groupA",
        }
        self.assertEqual(result, expected)

    def test_even_distribution_assignment_exact_division(self):
        items = ["item1", "item2", "item3", "item4"]
        groups = ["groupA", "groupB"]
        strategy = TalkoEvenDistributionAssignment[str]()
        result = strategy.assign(items, groups)

        # Each group should get 2 items
        counts = {group: list(result.values()).count(group) for group in groups}
        self.assertEqual(counts["groupA"], 2)
        self.assertEqual(counts["groupB"], 2)

    def test_even_distribution_assignment_with_remainder(self):
        items = ["item1", "item2", "item3", "item4", "item5"]
        groups = ["groupA", "groupB"]
        strategy = TalkoEvenDistributionAssignment[str]()
        result = strategy.assign(items, groups)

        # One group gets 3, the other gets 2
        counts = {group: list(result.values()).count(group) for group in groups}
        self.assertIn(counts["groupA"], [2, 3])
        self.assertIn(counts["groupB"], [2, 3])
        self.assertEqual(sum(counts.values()), 5)

    def test_empty_items_list(self):
        items = []
        groups = ["groupA", "groupB"]
        strategy = TalkoRoundRobinAssignment[str]()
        result = strategy.assign(items, groups)
        self.assertEqual(result, {})

    def test_empty_groups_list(self):
        items = ["item1", "item2"]
        groups = []

        # TalkoRoundRobinAssignment should raise StopIteration
        strategy = TalkoRoundRobinAssignment[str]()
        with self.assertRaises(StopIteration):
            strategy.assign(items, groups)

        # TalkoEvenDistributionAssignment should raise ZeroDivisionError
        strategy = TalkoEvenDistributionAssignment[str]()
        with self.assertRaises(ZeroDivisionError):
            strategy.assign(items, groups)

    def test_base_assignment_strategy_assign_does_nothing(self):
        base_strategy = TalkoBaseAssignmentStrategy[str]()
        result = base_strategy.assign(["item1"], ["group1"])
        self.assertIsNone(result)
