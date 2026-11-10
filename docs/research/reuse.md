# Reuse and reproducibility

Use `/research/data/` to select a specific public projection and citation. Include
the release ID, original-source attribution, important qualifications, CC BY 4.0
credit and a description of changes. The historical canonical database and the
new public research projection have different version identities.

The edition package includes a SHA-256 inventory, schemas, methods and SQLite,
CSV and JSON exports of the same approved records. Reproduce a table from the
included projection rather than fetching mutable current pages. Run the package's
reproduction command and compare its manifest; network access is unnecessary.

Example SQLite inspection (use the actual release's table/column documentation):

```python
import sqlite3
with sqlite3.connect("research-graph.sqlite") as database:
    assert database.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    print(database.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall())
```

Examples and schemas must be shipped with the actual package. Citation metadata
describes DOI status honestly; prepublication URLs are not invented DOI records.

To report a public reuse, use the Reuse Issue Form linked from `/review/`. A
download, visit or repository star is an activity proxy, not proof of adoption.
