from itertools import chain, cycle, islice
from typing import Dict, Generic, List, TypeVar

T = TypeVar("T")  # Generic type variable


class BaseAssignmentStrategy(Generic[T]):
    """Base class for generic assignment strategies."""

    def assign(self, items: List[T], groups: List[T]) -> Dict[T, T]:
        """Assign items to groups."""
        pass


class RoundRobinAssignment(BaseAssignmentStrategy[T]):
    """Assigns items in a round-robin fashion with a specified starting index."""

    def assign(
        self, items: List[T], groups: List[T], start_index: int = 0
    ) -> Dict[T, T]:
        if not groups:
            raise StopIteration("Cannot assign items to empty groups list")
        assigned_to_cycle = cycle(
            chain(islice(groups, start_index, None), groups[:start_index])
        )  # Use chain instead of +
        return {item: next(assigned_to_cycle) for item in items}


class EvenDistributionAssignment(BaseAssignmentStrategy[T]):
    """Ensures an even distribution of items across groups."""

    def assign(self, items: List[T], groups: List[T]) -> Dict[T, T]:
        assignments = {}
        chunk_size = len(items) // len(groups)  # Base number of items per group
        extra = len(items) % len(groups)  # Handle remainder
        item_index = 0
        for group in groups:
            count = chunk_size + (1 if extra > 0 else 0)  # Distribute remainder evenly
            extra -= 1 if extra > 0 else 0
            for _ in range(count):
                assignments[items[item_index]] = group
                item_index += 1
        return assignments
