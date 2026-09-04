import inspect
import logging
import logging.config

from starlette_context import context
from starlette_context.plugins.request_id import RequestIdPlugin

from src.config.log import LOGGING_CONFIG
from src.loggers import TalkoLogLevel

from ..exceptions import TalkoLoggerException


class TalkoRequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool | logging.LogRecord:
        try:
            record.request_id = context[RequestIdPlugin.key]
        except Exception:
            # No context available (e.g., Celery task)
            record.request_id = "no-request-id"
        return True


class TalkoBaseLogger:
    __logger = None
    LOG_LEVEL = "DEBUG"

    @classmethod
    def get_logger(cls):
        """steup and return logger"""
        if cls.__logger:
            return cls.__logger
        # cls._load_dict_conf()
        cls.__logger = logging.getLogger(cls._type())

        cls._set_file_handler()
        cls._set_stream_handler()

        # cls._add_filter()
        # set log level
        cls._set_log_level()
        cls.get_logger()
        return cls.__logger

    @classmethod
    def _set_file_handler(cls):
        fh = logging.FileHandler("console_service.log")
        fh.addFilter(TalkoRequestIdFilter())
        fh.setFormatter(cls._get_log_format())
        cls.__logger.addHandler(fh)

    @classmethod
    def _set_stream_handler(cls):
        sh = logging.StreamHandler()
        sh.addFilter(TalkoRequestIdFilter())
        sh.setFormatter(cls._get_log_format())
        cls.__logger.addHandler(sh)

    @classmethod
    def _get_log_format(cls):
        return logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(process)d %(thread)d - Log ID: %(request_id)s %(message)s"
        )

    @classmethod
    def _add_filter(cls):
        cls.__logger.addFilter(TalkoRequestIdFilter())

    @classmethod
    def _type(cls):
        return cls.__class__.__name__

    @classmethod
    def _load_dict_conf(cls):
        logging.config.dictConfig(LOGGING_CONFIG)

    @classmethod
    def _set_log_level(cls):
        cls.__logger.setLevel(cls.__get_log_level(TalkoLogLevel.Level.DEBUG))

    def _log_with_context(self, level, message: str):
        # Get the previous frame in the stack, skipping the logger's internal calls
        frame = inspect.currentframe().f_back.f_back  # Move back to the caller's frame
        line_number = frame.f_lineno
        module_name = frame.f_globals["__name__"]

        # Prepare the log message with line number and module name
        original_message = "({}:{}) {}".format(module_name, line_number, message)
        self.__logger.log(level, original_message)

    def debug(self, message: str):
        self._log_with_context(logging.DEBUG, message)

    def info(self, message: str):
        self._log_with_context(logging.INFO, message)

    def warning(self, message: str):
        self._log_with_context(logging.WARNING, message)

    def critical(self, message: str):
        self._log_with_context(logging.CRITICAL, message)

    def error(self, message: str):
        self._log_with_context(logging.ERROR, message)

    @classmethod
    def __get_log_level(cls, level: TalkoLogLevel.Level) -> int:
        match level:
            case TalkoLogLevel.Level.DEBUG:
                return logging.DEBUG
            case TalkoLogLevel.Level.INFO:
                return logging.INFO
            case TalkoLogLevel.Level.WARNING:
                return logging.WARNING
            case TalkoLogLevel.Level.CRITICAL:
                return logging.CRITICAL
            case TalkoLogLevel.Level.ERROR:
                return logging.ERROR
            case _:
                raise Exception(f"log level not found - {level.name}")
