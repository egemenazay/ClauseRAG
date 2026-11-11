from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PyPdfError

MAX_UPLOAD_MB = 10
MAX_PAGES = 30
MAX_CHARACTERS = 60_000


class DocumentError(ValueError):
    """Kullanıcıya gösterilebilen belge okuma hatası."""


@dataclass(frozen=True)
class Page:
    number: int
    text: str


@dataclass(frozen=True)
class Document:
    name: str
    pages: tuple[Page, ...]

    @property
    def unreadable_pages(self) -> tuple[int, ...]:
        return tuple(page.number for page in self.pages if not page.text)


def read_pdf(name: str, content: bytes) -> Document:
    if len(content) > MAX_UPLOAD_MB * 1024**2:
        raise DocumentError(f"PDF boyutu {MAX_UPLOAD_MB} MB sınırını aşıyor.")
    if b"%PDF-" not in content[:1024]:
        raise DocumentError("Dosya geçerli bir PDF olarak okunamadı.")

    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            raise DocumentError("PDF şifreli. Şifresiz bir kopya yükleyin.")
        if len(reader.pages) > MAX_PAGES:
            raise DocumentError(f"PDF {MAX_PAGES} sayfa sınırını aşıyor.")

        pages = []
        character_count = 0
        for number, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text().strip()
            except (PyPdfError, ValueError, TypeError, KeyError, IndexError):
                text = ""
            character_count += len(text)
            if character_count > MAX_CHARACTERS:
                raise DocumentError("Belge metni 60.000 karakter sınırını aşıyor.")
            pages.append(Page(number, text))
    except DocumentError:
        raise
    except (PyPdfError, ValueError, TypeError, KeyError, IndexError, RecursionError) as error:
        raise DocumentError("PDF okunamadı. Dosyayı yeniden kaydedip yükleyin.") from error

    if not any(page.text for page in pages):
        raise DocumentError("PDF’de seçilebilir metin bulunamadı. Metin tabanlı bir PDF yükleyin.")
    return Document(name, tuple(pages))
