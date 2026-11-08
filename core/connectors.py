"""Data connectors. Option B pulls block data from SAP on a schedule instead of a manual upload.

The prototype has no SAP system to call, so SapConnector is SIMULATED: it produces the extract from the
bundled sample file, in the same format a real SAP Datasphere or OData extract would be mapped to.
Swapping in the real connection changes only `_fetch`; the pipeline after it stays the same.
"""
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

SAP_CONFIG = {
    "System": "SAP S/4HANA (simulated in this prototype)",
    "Route": "SAP Datasphere replication flow to a CSV/Parquet extract",
    "Data": "Block harvest cycles: yield, fertilizer, leaf samples, pests, field conditions",
    "Schedule": "Daily at 02:00, after field data is posted",
    "Checks": "Same 117-column schema and 22 quality checks as a manual upload",
}


class SapConnector:
    simulated = True

    def __init__(self, sample_path):
        self.sample_path = Path(sample_path)

    def _fetch(self, dest):
        # Real system: query the SAP extract here. Prototype: copy the sample in the same schema.
        shutil.copyfile(self.sample_path, dest)

    def extract(self, dest_dir):
        """Pull the latest extract into dest_dir; return (file path, summary)."""
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        dest = dest_dir / f"sap_extract_{now:%Y%m%d_%H%M%S}.csv"
        self._fetch(dest)
        d = pd.read_csv(dest, encoding="utf-8-sig", usecols=lambda c: c in {"block_id", "estate_name", "harvest_cycle_no"})
        summary = {"synced_at": now.isoformat(timespec="seconds"), "rows": len(d), "blocks": int(d.block_id.nunique()),
                   "estates": int(d.estate_name.nunique()), "cycles": int(d.harvest_cycle_no.nunique()), "file": dest.name}
        return dest, summary
