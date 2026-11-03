"""Provider-neutral structured generation and durable, owner-scoped analysis jobs.

Providers are reusable by future coach/report services. Commands enqueue without
committing; the application worker is the only component invoking providers.
"""
