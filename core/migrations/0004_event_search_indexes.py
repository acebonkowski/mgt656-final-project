"""
Indexes for event search (#35).

- B-tree indexes on end_at (every search and the map filter on upcoming
  events), start_at (result order, date range) and category.
- Postgres only: a GIN index on the weighted full-text expression used by
  core.search._filter_text (name weight A, description weight B, "english").
  It must stay identical to that expression, or Postgres won't use it.

The indexes are created with the schema editor rather than declared in
Event.Meta, so core/models.py (owned by #31) is unchanged. SQLite (local
development only) gets the B-tree indexes and skips the GIN index.
"""

from django.db import migrations, models

BTREE_INDEXES = [
    ("core_event_end_at_idx", ["end_at"]),
    ("core_event_start_at_idx", ["start_at"]),
    ("core_event_category_idx", ["category"]),
]
FULL_TEXT_INDEX = "core_event_search_gin"


def full_text_index():
    from django.contrib.postgres.indexes import GinIndex
    from django.contrib.postgres.search import SearchVector

    return GinIndex(
        SearchVector("name", weight="A", config="english")
        + SearchVector("description", weight="B", config="english"),
        name=FULL_TEXT_INDEX,
    )


def indexes(schema_editor):
    result = [models.Index(fields=fields, name=name) for name, fields in BTREE_INDEXES]
    if schema_editor.connection.vendor == "postgresql":
        result.append(full_text_index())
    return result


def add_indexes(apps, schema_editor):
    event = apps.get_model("core", "Event")
    for index in indexes(schema_editor):
        schema_editor.add_index(event, index)


def remove_indexes(apps, schema_editor):
    event = apps.get_model("core", "Event")
    for index in indexes(schema_editor):
        schema_editor.remove_index(event, index)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_event"),
    ]

    operations = [
        migrations.RunPython(add_indexes, remove_indexes),
    ]
