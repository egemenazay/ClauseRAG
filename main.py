import os
from dataclasses import dataclass
from time import perf_counter

import streamlit as st

from clauserag.analysis import AnalysisError, AnalysisResult, FullContextAnalysis
from clauserag.demo import SAMPLE_PDF, load_demo
from clauserag.documents import MAX_CHARACTERS, MAX_PAGES, MAX_UPLOAD_MB, Document, DocumentError, read_pdf
from clauserag.openai_model import OpenAIRiskModel


@dataclass(frozen=True)
class DisplayedAnalysis:
    document: Document
    result: AnalysisResult
    elapsed: float | None = None


def clear_analysis() -> None:
    st.session_state.pop("analysis", None)


def run_live(name: str, content: bytes, api_key: str) -> DisplayedAnalysis:
    start = perf_counter()
    document = read_pdf(name, content)
    result = FullContextAnalysis(OpenAIRiskModel(api_key)).analyze(document)
    return DisplayedAnalysis(document, result, perf_counter() - start)


def show_analysis(analysis: DisplayedAnalysis) -> None:
    document, result = analysis.document, analysis.result
    st.header("Risk bulguları")
    st.text(document.name)

    if analysis.elapsed is None:
        st.info("Hazır örnek · Sentetik poliçe ve önceden hazırlanmış bulgular gösteriliyor.")
    else:
        st.caption(f"{result.method} · {result.model}")
        st.metric("Toplam analiz süresi", f"{analysis.elapsed:.2f} sn".replace(".", ","))

    if document.unreadable_pages:
        page_numbers = ", ".join(map(str, document.unreadable_pages))
        st.warning(f"Metin çıkarılamadığı için inceleme dışında kalan sayfalar: {page_numbers}.")
    if result.discarded_count:
        st.warning(f"Kanıtı doğrulanamayan veya eksik olan {result.discarded_count} bulgu elendi.")
    if not result.findings:
        st.info("Doğrulanmış risk bulgusu bulunamadı.")
        return

    st.caption(f"{len(result.findings)} doğrulanmış bulgu · {len(document.pages)} PDF sayfası")
    badge_colors = {"Yüksek": "red", "Orta": "orange", "Düşük": "blue"}
    for finding in result.findings:
        with st.container(border=True):
            st.badge(f"{finding.severity} önem", color=badge_colors[finding.severity])
            st.subheader(finding.category)
            st.text(finding.rationale)
            for source in finding.evidence:
                st.caption(f"PDF · Sayfa {source.page}")
                st.text(f"“{source.quote}”")


def main() -> None:
    st.set_page_config(page_title="ClauseRAG | Poliçe ve sözleşme inceleme", page_icon="📄")
    st.html("""
        <style>
          [data-testid="stMainBlockContainer"] { max-width: 58rem; padding-top: 3rem; }
          [data-testid="stText"] { white-space: pre-wrap; overflow-wrap: anywhere; }
          .clause-header {
            padding: clamp(1.3rem, 4vw, 2.4rem);
            background: #133d34; color: #f4f8f5;
            border-radius: 1.1rem; margin-bottom: 1rem;
          }
          .clause-header span { color: #a4dac7; font-weight: 700; }
          .clause-header h1 {
            color: inherit; font-size: clamp(1.8rem, 4vw, 2.65rem);
            letter-spacing: -.035em; padding: .35rem 0 .5rem;
          }
          .clause-header p { margin: 0; color: #dbece4; }
        </style>
        <header class="clause-header">
          <span>ClauseRAG</span>
          <h1>Poliçe ve sözleşme inceleme</h1>
          <p>PDF’nizdeki riskli maddeleri, olası etkileri ve sayfa alıntılarıyla inceleyin.</p>
        </header>
        """)

    with st.container(border=True):
        st.subheader("PDF yükle")
        uploaded = st.file_uploader(
            "Metin tabanlı PDF",
            type=["pdf"],
            key="pdf",
            on_change=clear_analysis,
        )
        character_limit = f"{MAX_CHARACTERS:,}".replace(",", ".")
        st.caption(
            f"En fazla {MAX_UPLOAD_MB} MB, {MAX_PAGES} sayfa ve "
            f"{character_limit} karakter."
        )
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if api_key:
            st.caption("Canlı analiz başlatıldığında PDF’den çıkarılan metin OpenAI API’ye gönderilir.")
        else:
            st.caption("Canlı analiz için OPENAI_API_KEY gerekli. Hazır örnek çevrimdışı açılabilir.")
        analyze = st.button("Analiz et", type="primary", disabled=uploaded is None or not api_key)

    st.subheader("Sentetik örnek poliçe")
    st.caption("Canlı analiz için örnek PDF’yi indirip yükleyebilir veya hazır bulguları açabilirsiniz.")
    sample, download = st.columns(2)
    show_sample = sample.button("Hazır örneği göster")
    download.download_button(
        "Örnek PDF’yi indir",
        data=SAMPLE_PDF.read_bytes(),
        file_name=SAMPLE_PDF.name,
        mime="application/pdf",
        on_click="ignore",
    )

    if analyze and uploaded is not None:
        clear_analysis()
        try:
            with st.spinner("PDF okunuyor ve riskli maddeler inceleniyor…"):
                st.session_state.analysis = run_live(uploaded.name, uploaded.getvalue(), api_key)
        except (DocumentError, AnalysisError) as error:
            st.error(str(error))
    elif show_sample:
        document, result = load_demo()
        st.session_state.analysis = DisplayedAnalysis(document, result)

    if "analysis" in st.session_state:
        show_analysis(st.session_state.analysis)


if __name__ == "__main__":
    main()
