"""Credential-safe logging utilities.

SEC-02: Ensures credentials never appear in log output.
"""
import logging
import re
from typing import List, Tuple, Pattern


class CredentialFilter(logging.Filter):
    """Logging filter that masks sensitive data in log records.

    Automatically applied to all loggers via setup_logging().
    Masks common credential patterns: password, pwd, secret, key, token.
    """

    # Patterns to mask (compiled regex, replacement text)
    PATTERNS: List[Tuple[Pattern[str], str]] = [
        # password="value" or password: value or password=value
        (re.compile(r'password["\']?\s*[:=]\s*["\']?[^"\'\s;,}]+', re.I), 'password=***'),
        # pwd="value" (ODBC style)
        (re.compile(r'pwd["\']?\s*[:=]\s*["\']?[^"\'\s;,}]+', re.I), 'pwd=***'),
        # secret="value"
        (re.compile(r'secret["\']?\s*[:=]\s*["\']?[^"\'\s;,}]+', re.I), 'secret=***'),
        # api_key="value" or apikey="value"
        (re.compile(r'api[_-]?key["\']?\s*[:=]\s*["\']?[^"\'\s;,}]+', re.I), 'api_key=***'),
        # token="value"
        (re.compile(r'token["\']?\s*[:=]\s*["\']?[^"\'\s;,}]+', re.I), 'token=***'),
        # fernet_key="value"
        (re.compile(r'fernet[_-]?key["\']?\s*[:=]\s*["\']?[^"\'\s;,}]+', re.I), 'fernet_key=***'),
        # Bearer tokens
        (re.compile(r'Bearer\s+[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', re.I), 'Bearer ***'),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        """Mask sensitive data in the log record message.

        Args:
            record: Log record to filter

        Returns:
            True (always allow record through, but with masked content)
        """
        if hasattr(record, 'msg') and isinstance(record.msg, str):
            for pattern, replacement in self.PATTERNS:
                record.msg = pattern.sub(replacement, record.msg)

        # Also filter args if they're strings
        if record.args:
            new_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    masked = arg
                    for pattern, replacement in self.PATTERNS:
                        masked = pattern.sub(replacement, masked)
                    new_args.append(masked)
                else:
                    new_args.append(arg)
            record.args = tuple(new_args)

        return True


def setup_logging(level: int = logging.INFO) -> None:
    """Configure application logging with credential filtering.

    Call this early in application startup to ensure all logs are filtered.

    Args:
        level: Logging level (default: INFO)
    """
    # Configure root logger
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    # Add credential filter to root logger (affects all handlers)
    root_logger = logging.getLogger()
    credential_filter = CredentialFilter()
    root_logger.addFilter(credential_filter)

    # Also add to any existing handlers
    for handler in root_logger.handlers:
        handler.addFilter(credential_filter)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger with credential filtering
    """
    return logging.getLogger(name)
