# snakelit

Reusable Streamlit widgets for Snakemake workflows.

`snakelit` collects the UI pieces that otherwise get copied between the Snakemake workflow catalog's browser app and SRPtn.

## Features
### File explorer

`FileExplorer` knows nothing about the filesystem. Implement `FileStore` and
hand it over:

```python
import streamlit as st

from snakelit.file_explorer import FileExplorer
from snakelit.types import FileStore, Stat


class MemoryStore(FileStore): ...


if "explorer" not in st.session_state:
    st.session_state["explorer"] = FileExplorer(
        "files", MemoryStore({"notes.txt": b"hello\n"})
    )

st.session_state["explorer"].render()
```

Click the folder and files to preview and edit, supports uploads and downloads.
`FileExplorer(..., on_zip=callback)` adds an "Unzip and trigger merge" action for a single uploaded `.zip`; the callback receives `(name, bytes)` and returns whether the page should rerun.

### Schema-driven editors

`snakelit` enables edit configfiles and tables with optional schema.
Schemas are read-only and used to choose widgets, coerce values and report errors.

#### Configuration

`schema_config` renders a config document as a form and falls back to a raw YAML/JSON editor.

```python
from snakelit.editor.config import schema_config

errors: list[str] = []
updated = schema_config(
    data,
    errors,
    schema,
    header="Workflow configuration",
    key="config",
    format="yaml",
)
if updated is not None:
    store.write("config/config.yaml", updated)
for message in errors:
    st.error(message)
```

Passing `edit_file=callback` adds a button next to string values that look like paths; the host decides whether to open or create the file.

#### Tables

`schema_table` does the same for tables and uses the declared row schema to cast columns before editing and validate every row afterwards. It needs the `tables` extra and accepts `csv`, `tsv`, `parquet` and `xlsx`:

```python
from snakelit.editor.table import schema_table

errors: list[str] = []
updated = schema_table(
    data,
    errors,
    schema,
    key="samples",
    format="tsv",
)
```

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
pip install "snakelit[tables]"   # table editor and table preview
```

Python 3.11+ and Streamlit 1.55+.

## Development

```bash
pixi run -e test pytest -q
pixi run -e publish check
```
