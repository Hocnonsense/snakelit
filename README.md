snakelit
========

Reusable Streamlit widgets for Snakemake workflows.

`snakelit` collects the UI pieces that otherwise get copied between the Snakemake workflow catalog's browser app and SRPtn.

## Features

### Schemas

Schemas are optional and read-only. The host supplies the parsed schema and decides where it comes from. `create_form` uses it for field widgets; `schema_config` validates config edits; `schema_table` uses it for column coercion and row validation.

For string values that look like paths, `create_form(..., edit_file=callback)` adds a button. The callback receives the path; the host decides whether to open, create or ignore it.

### Schema-driven editors

`snakelit` enables edit configfiles and tables with optional schema.
Schemas are read-only and used to choose widgets, coerce values and report errors.

Both file editors delegate mode selection, raw text editing, validation before write-back, and change detection in text mode to `schema_editor`. Each supplies its optional form renderer, a `can_text` flag, and a `validate(data, schema)` callback.
The validator checks the proposed file bytes on either path, or the original bytes when unchanged. They share an optional **View schema** toggle. The read-only reference starts closed and can be opened in either mode.

#### Configuration

`schema_config(data, errors, schema, ...)` combines Form and Text modes and preserves the original bytes when the form is untouched. Mappings use field widgets and nested tabs; a list or scalar root uses a single Value widget.
Use `snakelit.editor.config.create_form` to edit a mapping in place.

```python
from snakelit.editor.config import schema_config

updated = schema_config(
    data,
    [],
    schema,
    *,
    key="config",
    format="yaml",
)
```

Passing `edit_file=callback` adds a button next to string values that look like paths; the host decides whether to open or create the file.

#### Tables

`schema_table` does the same for tables and uses the declared row schema to cast columns before editing and validate every row afterwards. It needs the `tables` extra and accepts `csv`, `tsv`, `parquet` and `xlsx`:
`snakelit.editor.table.create_form` renders an in-memory DataFrame.

```python
from snakelit.editor.table import schema_table

updated = schema_table(
    data,
    [],
    schema,
    key="samples",
    format="tsv",
)
```

### Select repository and version picker

Use `repository_picker(repositories, initial=..., key=...)` from `snakelit.version_picker` to choose a host-supplied repository or enter a URL.
Pass a ref loader for the selected repository to `version_picker`, with a repository-specific widget key.

### Refs

`version_picker(init_ref, load, key=...)` asks the host for refs lazily via `load(kind)`, where `kind` is `"tag"`, `"branch"` or `"commit"`. The host can serve them from its own workflow store or from the GitHub API.

### Merge view

```python
from snakelit.merge import diff_files, render_merge

render_merge(
    store,
    "Merge me/wf@main (abc1234)",
    diff_files(store, incoming),
    base=original_files,
)
```

Rows can be applied, finished or deleted; an empty dict means the merge is complete.

## Install

```bash
pip install snakelit
pip install "snakelit[widgets]"  # ACE, unique string tags and drag sorting
pip install "snakelit[tables]"   # table editor and table preview
```

Python 3.11+ and Streamlit 1.55+.

## Development

```bash
pixi run -e test pytest -q
pixi run -e publish check
```
