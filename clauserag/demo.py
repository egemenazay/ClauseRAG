from pathlib import Path

from .analysis import AnalysisResult, ModelOutput, verify_findings
from .documents import Document, read_pdf

DEMO_DIR = Path(__file__).with_name("demo_data")
SAMPLE_PDF = DEMO_DIR / "ornek-police.pdf"


def load_demo() -> tuple[Document, AnalysisResult]:
    document = read_pdf(SAMPLE_PDF.name, SAMPLE_PDF.read_bytes())
    output = ModelOutput.model_validate_json((DEMO_DIR / "bulgular.json").read_text(encoding="utf-8"))
    return document, verify_findings(document, output, "Hazır örnek", None)
