import os
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import httpx
import openai
from streamlit.testing.v1 import AppTest

from clauserag.analysis import ModelOutput
from clauserag.demo import DEMO_DIR, SAMPLE_PDF


class AppTests(TestCase):
    def test_demo_without_api_key(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            app = AppTest.from_file("../main.py").run()
            self.assertTrue(app.button[0].proto.disabled)
            app.button[1].click().run()
        self.assertFalse(app.exception)
        self.assertIn("Hazır örnek", app.info[0].value)
        self.assertIn("Risk bulguları", [heading.value for heading in app.header])
        self.assertIn("PDF · Sayfa 2", [caption.value for caption in app.caption])

    def test_uploaded_pdf_live_flow_can_retry_after_timeout(self):
        model_output = ModelOutput.model_validate_json(
            (DEMO_DIR / "bulgular.json").read_text(encoding="utf-8")
        )
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}),
            patch("clauserag.openai_model.openai.OpenAI") as client,
        ):
            response = client.return_value.responses.parse
            response.side_effect = [
                openai.APITimeoutError(httpx.Request("POST", "https://example.test")),
                SimpleNamespace(status="completed", output_parsed=model_output),
                SimpleNamespace(status="completed", output_parsed=ModelOutput(findings=[])),
            ]
            app = AppTest.from_file("../main.py").run()
            app.file_uploader[0].upload(SAMPLE_PDF.name, SAMPLE_PDF.read_bytes(), "application/pdf").run()
            self.assertFalse(app.button[0].proto.disabled)
            app.button[0].click().run()
            self.assertIn("zaman aşımına", app.error[0].value)
            self.assertFalse(app.button[0].proto.disabled)

            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertFalse(app.error)
            self.assertIn("Full-Context LLM · gpt-5.4-mini", [caption.value for caption in app.caption])
            self.assertEqual(app.metric[0].label, "Toplam analiz süresi")
            self.assertIn("PDF · Sayfa 2", [caption.value for caption in app.caption])
            self.assertEqual(response.call_args.kwargs["model"], "gpt-5.4-mini")

            app.button[0].click().run()
            self.assertIn("Doğrulanmış risk bulgusu bulunamadı.", [info.value for info in app.info])

            app.file_uploader[0].clear().run()
            self.assertFalse(app.header)
