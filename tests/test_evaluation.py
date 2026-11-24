import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from clauserag.analysis import ModelOutput
from evaluation.evaluate import read_json, run, selected_documents, write_json


class EvaluationTests(TestCase):
    def test_diagnostics_are_saved_and_resume_checks_analysis_version(self):
        entry = next(item for item in selected_documents("test") if item["id"] == "knt-01")
        output = ModelOutput.model_validate({"findings": [{
            "category": "Muafiyet ve limitler",
            "severity": "Düşük",
            "rationale": "Cihaz başına 50 TL muafiyet uygulanır.",
            "evidence": [{"page": 5, "quote": "beher cihaza 50.- TL tenzili muafiyet uygulanır."}],
        }, {
            "category": "Muafiyet ve limitler",
            "severity": "Orta",
            "rationale": "Belgede bulunmayan sonuç.",
            "evidence": [{"page": 5, "quote": "Uydurulmuş alıntı."}],
        }]})
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch("evaluation.evaluate.selected_documents", return_value=[entry]),
            patch("evaluation.evaluate.OpenAIRiskModel.detect", return_value=output) as detect,
            patch("builtins.print"),
        ):
            directory = Path(temporary)
            run("test", directory, "test-key")
            saved = read_json(directory / "knt-01.json")
            self.assertEqual(len(saved["findings"]), 1)
            self.assertEqual(saved["findings"][0]["evidence"][0]["page"], 1)
            self.assertEqual(saved["raw_findings"][0]["evidence"][0]["page"], 5)
            self.assertEqual(saved["discarded_count"], 1)
            self.assertEqual(saved["discarded_findings"], [{
                "finding_index": 2, "reason": "quote_not_found", "evidence_index": 1,
            }])
            self.assertEqual(saved["evidence_corrections"], [{
                "finding_index": 1, "evidence_index": 1, "requested_page": 5, "actual_page": 1,
            }])

            run("test", directory, "test-key")
            detect.assert_called_once()
            with patch("evaluation.evaluate.analysis_fingerprint", return_value="changed"):
                with self.assertRaisesRegex(ValueError, "analiz sürümü farklı"):
                    run("test", directory, "test-key")

            metadata = read_json(directory / "run.json")
            metadata.pop("analysis_sha256")
            write_json(directory / "run.json", metadata)
            with self.assertRaisesRegex(ValueError, "Yeni bir çıktı klasörü"):
                run("test", directory, "test-key")
            detect.assert_called_once()
