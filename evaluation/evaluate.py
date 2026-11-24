import argparse
import csv
import hashlib
import json
import logging
import os
from dataclasses import asdict
from pathlib import Path
from statistics import median
from time import perf_counter

import openai

from clauserag.analysis import AnalysisError, FullContextAnalysis
from clauserag.documents import DocumentError, read_pdf
from clauserag.openai_model import OpenAIRiskModel


ROOT = Path(__file__).resolve().parent
REVIEW_FIELDS = ("belge_id", "dogru_bulgu", "gerekceyi_destekleyen_kanit")


def analysis_fingerprint():
    digest = hashlib.sha256()
    for name in ("analysis.py", "documents.py", "openai_model.py"):
        digest.update((ROOT.parent / "clauserag" / name).read_bytes())
    return digest.hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_document(entry):
    path = ROOT / entry["file"]
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != entry["sha256"]:
        raise ValueError(f"{entry['id']}: PDF, sabitlenen pilot sürümüyle eşleşmiyor.")
    document = read_pdf(path.name, content)
    if document.unreadable_pages or len(document.pages) != entry["pages"]:
        raise ValueError(f"{entry['id']}: PDF sayfaları beklenen biçimde okunamadı.")
    return document


def selected_documents(split):
    return [entry for entry in read_json(ROOT / "manifest.json")["documents"] if entry["split"] == split]


def run(split, output, api_key):
    entries = selected_documents(split)
    output.mkdir(parents=True, exist_ok=True)
    run_file = output / "run.json"
    run_info = {
        "split": split,
        "method": "Full-Context LLM",
        "model": OpenAIRiskModel.name,
        "manifest_sha256": hashlib.sha256((ROOT / "manifest.json").read_bytes()).hexdigest(),
        "analysis_sha256": analysis_fingerprint(),
    }
    if run_file.exists() and read_json(run_file) != run_info:
        raise ValueError("Bu klasörün belge seti, modeli veya analiz sürümü farklı. Yeni bir çıktı klasörü seçin.")
    if not run_file.exists() and any(output.iterdir()):
        raise ValueError("Çıktı için boş bir klasör seçin.")
    pending = [entry for entry in entries if not (output / f"{entry['id']}.json").exists()]
    write_json(run_file, run_info)

    response_details = {}

    def capture_usage(response):
        if response.is_success and response.request.url.path.endswith("/responses"):
            response.read()
            payload = response.json()
            response_details.update(model=payload.get("model"), usage=payload.get("usage"))

    failed = []
    if pending:
        model = OpenAIRiskModel(api_key)
        with model.client as original_client, openai.DefaultHttpxClient(
            event_hooks={"response": [capture_usage]}
        ) as http_client:
            model.client = original_client.with_options(http_client=http_client)
            strategy = FullContextAnalysis(model)
            for entry in pending:
                doc_id = entry["id"]
                response_details.clear()
                start = perf_counter()
                try:
                    result = strategy.analyze(read_document(entry))
                except (AnalysisError, DocumentError) as error:
                    if isinstance(error.__cause__, (openai.AuthenticationError, openai.PermissionDeniedError)):
                        raise ValueError(str(error)) from error
                    failed.append(doc_id)
                    print(f"{doc_id}: {error}", flush=True)
                    continue
                write_json(output / f"{doc_id}.json", {
                    "belge_id": doc_id,
                    "model": response_details.get("model"),
                    "usage": response_details.get("usage"),
                    "seconds": round(perf_counter() - start, 4),
                    "discarded_count": result.discarded_count,
                    "raw_findings": [finding.model_dump() for finding in result.raw_findings],
                    "discarded_findings": [asdict(item) for item in result.discarded_findings],
                    "evidence_corrections": [asdict(item) for item in result.evidence_corrections],
                    "findings": [finding.model_dump() for finding in result.findings],
                })
                print(
                    f"{doc_id}: {len(result.findings)} bulgu kaydedildi. "
                    f"{result.discarded_count} bulgu elendi. "
                    f"{len(result.evidence_corrections)} alıntının sayfası düzeltildi.",
                    flush=True,
                )
    if failed:
        raise ValueError(f"{len(failed)} belge tamamlanamadı. Aynı komutla kalan belgeleri tekrar çalıştırın.")

    review = output / "inceleme.csv"
    if not review.exists():
        with review.open("x", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            writer.writerow(REVIEW_FIELDS)
            writer.writerows((entry["id"], "", "") for entry in entries)
    print(f"Tahminler hazır. Elle puanlanacak dosya: {review}")


def score(output):
    run_info = read_json(output / "run.json")
    if run_info["manifest_sha256"] != hashlib.sha256((ROOT / "manifest.json").read_bytes()).hexdigest():
        raise ValueError("Çalıştırma, pilot setin farklı bir sürümüne ait.")
    entries = selected_documents(run_info["split"])
    with (output / "inceleme.csv").open(encoding="utf-8-sig", newline="") as stream:
        reviews = list(csv.DictReader(stream, delimiter=";"))
    review_index = {review["belge_id"]: review for review in reviews}
    if len(reviews) != len(review_index) or set(review_index) != {entry["id"] for entry in entries}:
        raise ValueError("İnceleme tablosunda her belge için bir satır olmalı.")

    report = {}
    for family in ("Sigorta", "Sözleşme"):
        tp = fp = fn = supported = discarded = 0
        timings = []
        token_usage = []
        for entry in entries:
            if entry["family"] != family:
                continue
            doc_id = entry["id"]
            result = read_json(output / f"{doc_id}.json")
            review = review_index[doc_id]
            try:
                matched = int(review["dogru_bulgu"])
                supported_count = int(review["gerekceyi_destekleyen_kanit"])
            except (ValueError, TypeError) as error:
                raise ValueError(f"{doc_id}: iki inceleme sayısını da tam sayı olarak girin.") from error
            predicted = len(result["findings"])
            expected = entry["expected_risks"]
            if not 0 <= matched <= min(predicted, expected) or not 0 <= supported_count <= predicted:
                raise ValueError(f"{doc_id}: inceleme sayıları beklenen ve tahmin edilen bulgularla uyuşmuyor.")
            tp += matched
            fp += predicted - matched
            fn += expected - matched
            supported += supported_count
            discarded += result["discarded_count"]
            timings.append(result["seconds"])
            token_usage.append(result["usage"])
        report[family] = {
            "belge": len(timings), "tp": tp, "fp": fp, "fn": fn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "f1": 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else None,
            "gerekceyi_destekleyen_kanit": supported,
            "uygulamada_elenen_bulgu": discarded,
            "toplam_saniye": round(sum(timings), 3),
            "medyan_saniye": round(median(timings), 3),
            "input_tokens": sum(usage["input_tokens"] for usage in token_usage) if all(token_usage) else None,
            "output_tokens": sum(usage["output_tokens"] for usage in token_usage) if all(token_usage) else None,
        }
    write_json(output / "puanlar.json", {"calistirma": run_info, "gruplar": report})
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main():
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    parser = argparse.ArgumentParser(description="ClauseRAG pilot değerlendirmesi")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate", help="PDF bütünlüğünü ve okunabilirliğini denetle")
    run_command = commands.add_parser("run", help="Tam PDF analizini ölç ve tahminleri kaydet")
    run_command.add_argument("--split", choices=("gelistirme", "test"), default="test")
    run_command.add_argument("--output", type=Path, required=True)
    score_command = commands.add_parser("score", help="Elle değerlendirilen tahminleri özetle")
    score_command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "validate":
            manifest = read_json(ROOT / "manifest.json")
            entries = manifest["documents"]
            reference = (ROOT / "degerlendirme.xlsx").read_bytes()
            if hashlib.sha256(reference).hexdigest() != manifest["reference_sha256"]:
                raise ValueError("Etiket tablosu sabitlenen pilot sürümüyle eşleşmiyor.")
            for entry in entries:
                read_document(entry)
            print(f"{len(entries)} PDF ve referans etiket tablosu doğrulandı.")
        elif args.command == "run":
            api_key = os.environ.get("OPENAI_API_KEY", "").strip()
            if not api_key:
                raise ValueError("Tam PDF ölçümü için OPENAI_API_KEY gerekli.")
            run(args.split, args.output, api_key)
        else:
            score(args.output)
    except (ValueError, OSError, DocumentError) as error:
        parser.exit(1, f"Hata: {error}\n")


if __name__ == "__main__":
    main()
