"""TEST-ONLY source roots use the same required owned inputs as real packages."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def populate_owned_inputs(destination):
    from research_citations import REPRODUCTION_INPUTS
    destination = Path(destination)
    for relative in REPRODUCTION_INPUTS.values():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
