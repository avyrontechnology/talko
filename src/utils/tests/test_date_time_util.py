import pytest

from src.utils.datetime_util import DateTimeUtil


class TestParseTimeStr:
    def test_parse_valid_range(self):
        # Arrange
        start = 1752410880000
        end = 1752411880000
        time_range = f"{start}-{end}"

        # Act
        result = DateTimeUtil.parse_time_str(time_range)

        # Assert
        assert result == (start, end)  # keep in milliseconds

    def test_parse_valid_range_equal_start_end(self):
        # Arrange
        ts = 1752410880000
        time_range = f"{ts}-{ts}"

        # Act
        result = DateTimeUtil.parse_time_str(time_range)

        # Assert
        assert result == (ts, ts)  # keep in milliseconds

    def test_parse_invalid_range_end_smaller_than_start(self):
        # Arrange
        start = 1752411880000
        end = 1752410880000
        time_range = f"{start}-{end}"

        # Act & Assert
        with pytest.raises(ValueError) as exc:
            DateTimeUtil.parse_time_str(time_range)
        assert "end timestamp must be greater than or equal" in str(exc.value)

    def test_parse_invalid_format_non_numeric(self):
        # Arrange
        time_range = "abc-def"

        # Act & Assert
        with pytest.raises(ValueError) as exc:
            DateTimeUtil.parse_time_str(time_range)
        assert "Issue with time_range" in str(exc.value)

    def test_parse_invalid_format_missing_dash(self):
        # Arrange
        time_range = "17524108800001752411880000"  # missing '-'

        # Act & Assert
        with pytest.raises(ValueError) as exc:
            DateTimeUtil.parse_time_str(time_range)
        assert "Issue with time_range" in str(exc.value)

    def test_parse_empty_string(self):
        assert DateTimeUtil.parse_time_str("") == (None, None)

    def test_parse_none(self):
        assert DateTimeUtil.parse_time_str(None) == (None, None)
