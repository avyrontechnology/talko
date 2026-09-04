import logging


class CeleryLogger:
    @staticmethod
    def get_logger() -> logging.Logger:
        """
        Returns a configured logger instance for Celery tasks.
        """
        logger = logging.getLogger("celery_logger")
        logger.setLevel(logging.DEBUG)

        if not logger.handlers:
            # Console handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.DEBUG)

            # File handler (optional)
            file_handler = logging.FileHandler("celery.log")
            file_handler.setLevel(logging.DEBUG)

            # Formatter
            formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] (%(module)s.%(funcName)s:%(lineno)d) %(message)s"
            )
            console_handler.setFormatter(formatter)
            file_handler.setFormatter(formatter)

            # Attach handlers
            logger.addHandler(console_handler)
            logger.addHandler(file_handler)

        return logger
