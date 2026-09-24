from datetime import datetime


class TalkoDateTimeUtil:
    @staticmethod
    def get_current_time() -> int:
        """Get the current time in milliseconds."""
        dt: datetime = datetime.now()
        return int(dt.timestamp() * 1000)

    @staticmethod
    def convert_date_time(data: str | int | None = None) -> int | None:
        """Convert datetime string or int to timestamp in milliseconds."""
        if data is None:
            return None

        if isinstance(data, int):
            return data

        if isinstance(data, datetime):
            return int(data.timestamp() * 1000)

        if isinstance(data, str):
            try:
                dt = datetime.strptime(data, "%Y-%m-%d %H:%M:%S")
                return int(dt.timestamp() * 1000)
            except ValueError:
                raise ValueError(f"Invalid datetime string format: {data}")

        raise TypeError(f"Unsupported data type: {type(data)}")

    @staticmethod
    def parse_time_str(time_range: str | None) -> tuple[int | None, int | None]:
        """Parse time_range string into start_date and end_date in seconds."""
        if not time_range:
            return None, None
        try:
            start_ms, end_ms = map(int, time_range.split("-"))
            if end_ms < start_ms:
                raise ValueError("end timestamp must be greater than or equal to start timestamp")
            return start_ms, end_ms
        except ValueError as e:
            raise ValueError(f"Issue with time_range. {e}")
