import json
from io import BytesIO
from unittest import TestCase
from unittest.mock import Mock, patch

from pypdf import PdfReader, PdfWriter

from clauserag.analysis import FullContextAnalysis, INSTRUCTIONS, ModelOutput
from clauserag.demo import SAMPLE_PDF, load_demo
from clauserag.documents import Document, DocumentError, Page, read_pdf


def make_pdf(*, blank_pages: int = 0, include_sample_page: bool = False, encrypt: bool = False) -> bytes:
    writer = PdfWriter()
    if include_sample_page:
        writer.add_page(PdfReader(SAMPLE_PDF).pages[0])
    for _ in range(blank_pages):
        writer.add_blank_page(width=300, height=400)
    if encrypt:
        writer.encrypt("password")
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


class DocumentTests(TestCase):
    def test_sample_is_two_pages_and_all_findings_match(self):
        document, result = load_demo()
        self.assertEqual([page.number for page in document.pages], [1, 2])
        self.assertEqual(len(result.findings), 4)
        self.assertEqual(result.discarded_count, 0)

    def test_blank_and_encrypted_documents(self):
        with self.assertRaisesRegex(DocumentError, "seçilebilir metin"):
            read_pdf("taranmis.pdf", make_pdf(blank_pages=1))
        with self.assertRaisesRegex(DocumentError, "şifreli"):
            read_pdf("sifreli.pdf", make_pdf(blank_pages=1, encrypt=True))
        with self.assertRaisesRegex(DocumentError, "geçerli bir PDF"):
            read_pdf("bozuk.pdf", b"invalid")

    def test_unreadable_page_keeps_its_number(self):
        document = read_pdf("karma.pdf", make_pdf(include_sample_page=True, blank_pages=1))
        self.assertEqual(document.unreadable_pages, (2,))

    def test_upload_limits(self):
        with self.assertRaisesRegex(DocumentError, "10 MB"):
            read_pdf("buyuk.pdf", bytes(10 * 1024**2 + 1))
        with self.assertRaisesRegex(DocumentError, "30 sayfa"):
            read_pdf("uzun.pdf", make_pdf(blank_pages=31))
        with patch("clauserag.documents.MAX_CHARACTERS", 20):
            with self.assertRaisesRegex(DocumentError, "60.000 karakter"):
                read_pdf("ornek.pdf", SAMPLE_PDF.read_bytes())


class AnalysisTests(TestCase):
    def setUp(self):
        self.document = Document(
            "police.pdf",
            (Page(1, "Her hasarda\n  15.000 TL muafiyet uygulanır."), Page(2, "Hasar bildirimi.")),
        )
        self.model = Mock(name="model")
        self.model.name = "test-model"
        self.strategy = FullContextAnalysis(self.model)

    def test_whole_document_is_sent_once_and_quotes_are_verified(self):
        valid = {"page": 1, "quote": "Her hasarda 15.000 TL muafiyet uygulanır."}
        self.model.detect.return_value = ModelOutput.model_validate(
            {
                "findings": [
                    {
                        "category": "Muafiyet ve limitler",
                        "severity": "Orta",
                        "rationale": "İlk 15.000 TL sigortalının üzerinde kalır.",
                        "evidence": sources,
                    }
                    for sources in (
                        [valid],
                        [dict(valid, page=2)],
                        [valid, {"page": 2, "quote": "Uydurma alıntı"}],
                        [],
                    )
                ]
            }
        )
        result = self.strategy.analyze(self.document)
        self.model.detect.assert_called_once()
        _, context = self.model.detect.call_args.args
        self.assertEqual(json.loads(context)["pages"], [
            {"page": page.number, "text": page.text} for page in self.document.pages
        ])
        self.assertEqual(len(result.findings), 2)
        self.assertEqual(result.findings[0].evidence[0].quote, valid["quote"])
        self.assertEqual(result.findings[1].evidence[0].page, 1)
        self.assertEqual(result.discarded_count, 2)
        self.assertEqual([item.reason for item in result.discarded_findings], ["quote_not_found", "missing_evidence"])
        self.assertEqual(len(result.evidence_corrections), 1)
        self.assertEqual(result.raw_findings[1].evidence[0].page, 2)

    def test_printed_page_number_is_resolved_to_physical_page(self):
        self.document = Document("kesit.pdf", (Page(1, "Sayfa: 5\nHer hasarda 15.000 TL muafiyet uygulanır."),))
        self.model.detect.return_value = ModelOutput.model_validate({"findings": [{
            "category": "Muafiyet ve limitler",
            "severity": "Orta",
            "rationale": "İlk 15.000 TL sigortalıya aittir.",
            "evidence": [{"page": 5, "quote": "Her hasarda 15.000 TL muafiyet uygulanır."}],
        }]})
        result = self.strategy.analyze(self.document)
        self.assertEqual(result.discarded_count, 0)
        self.assertEqual(result.findings[0].evidence[0].page, 1)
        correction, = result.evidence_corrections
        self.assertEqual((correction.finding_index, correction.evidence_index), (1, 1))
        self.assertEqual((correction.requested_page, correction.actual_page), (5, 1))
        self.assertEqual(result.raw_findings[0].evidence[0].page, 5)
        instructions, _ = self.model.detect.call_args.args
        self.assertEqual(instructions, INSTRUCTIONS)
        self.assertIn("fiziksel sayfa", instructions)

    def test_ambiguous_wrong_page_and_invented_or_empty_quotes_are_discarded(self):
        self.document = Document("tekrar.pdf", (
            Page(1, "Tekrarlanan hüküm."), Page(2, "Tekrarlanan hüküm."),
        ))
        sources = [
            [{"page": 5, "quote": "Tekrarlanan hüküm."}],
            [{"page": 5, "quote": "Uydurma alıntı."}],
            [{"page": 1, "quote": "   "}],
            [{"page": 2, "quote": "Tekrarlanan hüküm."}],
        ]
        self.model.detect.return_value = ModelOutput.model_validate({"findings": [{
            "category": "Muafiyet ve limitler", "severity": "Orta",
            "rationale": "Test açıklaması.", "evidence": evidence,
        } for evidence in sources]})
        result = self.strategy.analyze(self.document)
        self.assertEqual(len(result.findings), 1)
        self.assertEqual(result.findings[0].evidence[0].page, 2)
        self.assertEqual(result.evidence_corrections, ())
        self.assertEqual([item.reason for item in result.discarded_findings], [
            "ambiguous_quote", "quote_not_found", "empty_quote",
        ])
        self.assertEqual([item.finding_index for item in result.discarded_findings], [1, 2, 3])

    def test_rejected_finding_keeps_raw_evidence_without_committing_page_corrections(self):
        self.model.detect.return_value = ModelOutput.model_validate({"findings": [{
            "category": "Muafiyet ve limitler", "severity": "Orta", "rationale": "Test açıklaması.",
            "evidence": [
                {"page": 5, "quote": "15.000 TL muafiyet uygulanır."},
                {"page": 2, "quote": "Olmayan bir istisna."},
            ],
        }, {
            "category": "Muafiyet ve limitler", "severity": "Orta", "rationale": " ",
            "evidence": [{"page": 1, "quote": "15.000 TL muafiyet uygulanır."}],
        }]})
        result = self.strategy.analyze(self.document)
        self.assertEqual(result.findings, ())
        self.assertEqual(result.evidence_corrections, ())
        self.assertEqual(result.discarded_count, 2)
        self.assertEqual(result.discarded_findings[0].evidence_index, 2)
        self.assertEqual(result.discarded_findings[1].reason, "empty_rationale")
        self.assertEqual(result.raw_findings[0].evidence[0].page, 5)

    def test_empty_output(self):
        self.model.detect.return_value = ModelOutput(findings=[])
        result = self.strategy.analyze(self.document)
        self.assertEqual(result.findings, ())
        self.assertEqual(result.discarded_count, 0)
        self.assertEqual(result.raw_findings, ())
        self.assertEqual(result.discarded_findings, ())
        self.assertEqual(result.evidence_corrections, ())
