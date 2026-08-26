"""
M7: Audit Trail Subsystem
=========================
Minimal append-only audit trail recording decisions made by the
M3/M4/M6 pipeline.
"""

from ml.audit.audit_writer import (
    DEFAULT_DB_PATH,
    REQUIRED_AUDIT_FIELDS,
    initialise_db,
    write_record,
)

__all__ = [
    "DEFAULT_DB_PATH",
    "REQUIRED_AUDIT_FIELDS",
    "initialise_db",
    "write_record",
]
