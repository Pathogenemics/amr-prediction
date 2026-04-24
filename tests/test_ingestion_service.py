from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ingestion_service import ingest_single_fasta, read_batch_manifest, read_batch_status


class IngestSingleFastaTest(unittest.TestCase):
    def test_stores_single_fasta_in_bronze_and_writes_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            result = ingest_single_fasta(
                fasta_bytes=b">contig_1\nATGC\n",
                fasta_name="demo_001.fasta",
                data_root=temp_root / "data",
                batch_id="batch_single_001",
                biosample="demo_001",
            )

            stored_fasta_path = Path(result.stored_fasta_path)
            manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
            status = json.loads(Path(result.status_path).read_text(encoding="utf-8"))

            self.assertTrue(stored_fasta_path.exists())
            self.assertEqual(stored_fasta_path.read_text(encoding="utf-8"), ">contig_1\nATGC\n")
            self.assertEqual(result.batch_id, "batch_single_001")
            self.assertEqual(result.status, "ingested")
            self.assertEqual(manifest["batch_id"], "batch_single_001")
            self.assertIn("created_at", manifest)
            self.assertIn("updated_at", manifest)
            self.assertEqual(manifest["samples"][0]["biosample"], "demo_001")
            self.assertEqual(status["status"], "ingested")
            self.assertIn("created_at", status)
            self.assertIn("updated_at", status)

    def test_reads_saved_status_and_manifest_by_batch_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            ingest_single_fasta(
                fasta_bytes=b">contig_1\nATGC\n",
                fasta_name="demo_001.fasta",
                data_root=temp_root / "data",
                batch_id="batch_lookup_001",
                biosample="demo_001",
            )

            manifest = read_batch_manifest("batch_lookup_001", data_root=temp_root / "data")
            status = read_batch_status("batch_lookup_001", data_root=temp_root / "data")

            self.assertEqual(manifest["batch_id"], "batch_lookup_001")
            self.assertEqual(manifest["samples"][0]["biosample"], "demo_001")
            self.assertEqual(status["batch_id"], "batch_lookup_001")
            self.assertEqual(status["status"], "ingested")


if __name__ == "__main__":
    unittest.main()
