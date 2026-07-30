"""Enterprise connector layer: every data source conforms to one contract and
emits the common DatabaseSchema. Cross-cutting guards (read-only, row cap,
audit) are enforced at the contract, so they apply to every engine the same way.
"""
from app.services.connectors.base import (
    ReadOnlyConnector,
    WriteAttemptError,
    assert_read_only,
)

__all__ = ["ReadOnlyConnector", "WriteAttemptError", "assert_read_only"]
