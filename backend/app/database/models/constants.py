"""Schema constants that must not drift with runtime configuration.

These are baked into column types, so changing one is a migration plus a
backfill — not an environment variable.
"""

# `document_chunks.embedding`'s width. Matches text-embedding-3-small's default
# output; changing it means re-embedding the whole corpus.
EMBEDDING_DIMENSIONS = 1536
