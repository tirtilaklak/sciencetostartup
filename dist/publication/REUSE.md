# Reuse and reproducibility

Use `/research/data/` to select a specific public projection and citation. Include
the release ID, original-source attribution, important qualifications, CC BY 4.0
credit and a description of changes. The historical canonical database and the
new public research projection have different version identities.

The edition package includes a SHA-256 inventory, schemas, methods and SQLite,
CSV and JSON exports of the same approved records. Reproduce a table from the
included projection rather than fetching mutable current pages. Run the package's
reproduction command and compare its manifest; network access is unnecessary.

Extract the selected edition's archive and run `python3 reproduce.py --write-tables
reproduced` inside it. This verifies the manifest and reproduces the included
tables without network access. The JSON, CSV and SQLite files are three
representations of the same public projection.

Load the archived JSON and follow an approved assertion to its original source:

```python
import json
from pathlib import Path

data = json.loads(Path("clean-dataset.json").read_text(encoding="utf-8"))
graph = data["graph"]
sources = {source["id"]: source for source in graph["sources"]}
approved = [claim for claim in graph["assertions"] if claim["status"] == "approved"]
print(data["release_id"], len(approved), "approved assertions")
for claim in approved[:1]:
    print(claim["id"], claim["subject"], claim["predicate"], claim["value"])
    for evidence in claim["evidence"]:
        print(sources[evidence["source_id"]]["url"], evidence["locator"])
```

The archive's SQLite file uses a lossless `projection_rows` table. Open it read
only so a wrong filename cannot silently create an empty database:

```python
import json, sqlite3
from collections import Counter
from contextlib import closing

with closing(sqlite3.connect("file:clean-dataset.sqlite?mode=ro", uri=True)) as database:
    if database.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ValueError("SQLite integrity check failed")
    rows = database.execute(
        "SELECT value_json FROM projection_rows "
        "WHERE collection = 'graph.assertions' AND kind = 'record' ORDER BY position"
    )
    approved = [claim for (raw,) in rows if (claim := json.loads(raw))["status"] == "approved"]
    print(sorted(Counter(claim["predicate"] for claim in approved).items()))
```

When this edition is mirrored to Hugging Face, its public card provides an
anonymous loader with an immutable commit, edition checksum and release check.
Use the version DOI and citation shown for that edition; a current main branch
may contain a later edition. The frozen
package's citation status describes its preparation time. Examples and schemas
ship with the actual package; prepublication URLs are not invented DOI records.

To report a public reuse, use the Reuse Issue Form linked from `/review/`. A
download, visit or repository star is an activity proxy, not proof of adoption.
