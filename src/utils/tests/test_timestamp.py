import pytest

from src.utils import timestamped_model
from src.utils.timestamped_model import TalkoTimestampedModel

FAKE_TIMESTAMP = 1721635200


class TalkoFakeDateTimeUtil:
    def get_current_time(self):
        return FAKE_TIMESTAMP


def test_timestamps_set_if_not_provided(monkeypatch):
    """
    Test that created_at and updated_at are set if not provided.
    """
    # Patch TalkoDateTimeUtil to return a fixed timestamp
    monkeypatch.setattr(timestamped_model, "TalkoDateTimeUtil", lambda: TalkoFakeDateTimeUtil())

    model = TalkoTimestampedModel()

    assert model.created_at == FAKE_TIMESTAMP
    assert model.updated_at == FAKE_TIMESTAMP


def test_timestamps_preserved_if_provided(monkeypatch):
    """
    Test that created_at and updated_at are not overwritten if provided.
    """
    monkeypatch.setattr(
        "src.utils.timestamped_model.TalkoDateTimeUtil", lambda: TalkoFakeDateTimeUtil()
    )

    model = TalkoTimestampedModel(created_at=1111111111, updated_at=2222222222)

    assert model.created_at == 1111111111
    assert model.updated_at == 2222222222
