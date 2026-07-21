"""Shared persistence exception hierarchy for PaperScape repositories.

All repository methods raise these exceptions instead of raw ``sqlite3``,
``json``, or ``pydantic`` errors.  Original exceptions are preserved via
``raise ... from original`` (``__cause__``).

Safety
------
- Exception messages contain only IDs, status labels, type names, and
  error codes.
- Raw JSON, chunk text, evidence excerpts, prompts, model responses,
  credentials, and connection strings are **never** included.
"""
from __future__ import annotations


class PersistenceError(RuntimeError):
    """Base persistence failure — an operation against the database failed.

    The original ``sqlite3``, ``json``, or ``pydantic`` error is chained
    as ``__cause__``.
    """


class RecordNotFoundError(PersistenceError):
    """The requested persistence record does not exist."""


class InvalidJobTransitionError(PersistenceError):
    """The requested job-status transition is not allowed."""


class CorruptRecordError(PersistenceError):
    """Stored data cannot be reconstructed as the expected Pydantic model.

    Raised when:
    - Stored JSON is syntactically malformed (``json.JSONDecodeError``).
    - Stored JSON does not conform to the expected Pydantic schema
      (``pydantic.ValidationError``).
    - A decoded model's identity field (e.g. ``paper_id``) does not match
      the row's key column.
    """