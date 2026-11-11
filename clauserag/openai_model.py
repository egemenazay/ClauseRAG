import openai
from pydantic import ValidationError

from .analysis import AnalysisError, ModelOutput


class OpenAIRiskModel:
    name = "gpt-5.4-mini"

    def __init__(self, api_key: str):
        self.client = openai.OpenAI(api_key=api_key, timeout=60.0, max_retries=0)

    def detect(self, instructions: str, context: str) -> ModelOutput:
        try:
            response = self.client.responses.parse(
                model=self.name,
                instructions=instructions,
                input=context,
                text_format=ModelOutput,
                reasoning={"effort": "none"},
                max_output_tokens=12_000,
                store=False,
            )
        except openai.APITimeoutError as error:
            raise AnalysisError("Analiz zaman aşımına uğradı. Tekrar deneyin.") from error
        except (openai.AuthenticationError, openai.PermissionDeniedError) as error:
            raise AnalysisError("OpenAI API anahtarını ve model erişimini kontrol edin.") from error
        except openai.RateLimitError as error:
            raise AnalysisError("OpenAI API kota veya hız sınırına ulaştı. Hesabınızı kontrol edin.") from error
        except openai.APIConnectionError as error:
            raise AnalysisError("OpenAI API’ye bağlanılamadı. Bağlantınızı kontrol edip tekrar deneyin.") from error
        except (openai.APIError, ValidationError) as error:
            raise AnalysisError("OpenAI API analizi tamamlayamadı. Tekrar deneyin.") from error

        if response.status != "completed" or response.output_parsed is None:
            raise AnalysisError("Model tamamlanmış bir analiz döndürmedi. Tekrar deneyin.")
        return response.output_parsed
