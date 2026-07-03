import logging
import io
import pdfplumber
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from tools_impl.helpers import (
    _fetch_with_retry,
    _trim_to_sentence,
    MAX_PDF_CHARS,
)

logger = logging.getLogger(__name__)

class ExtractPDFInput(BaseModel):
    url: str = Field(
        ...,
        description=(
            "Direct URL to a PDF file (e.g. an arXiv PDF link). "
            "Must end with .pdf or return Content-Type: application/pdf."
        ),
    )

def _extract_pdf_from_bytes(content: bytes, source_url: str = "") -> str:
    """
    Shared PDF extraction logic, called by both extract_pdf tool and
    the content-type branch in scrape_url.
    """
    try:
        pages_text: list[str] = []
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            logger.info(
                "extract_pdf parsing | source=%s | pages=%d",
                source_url,
                len(pdf.pages),
            )
            for page_num, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    pages_text.append(f"[Page {page_num}]\n{page_text.strip()}")

        if not pages_text:
            return f"[EMPTY_PDF] No extractable text found in PDF at {source_url}."

        full_text = "\n\n".join(pages_text)
        trimmed = _trim_to_sentence(full_text, MAX_PDF_CHARS)

        logger.info(
            "extract_pdf completed | source=%s | pages_extracted=%d | chars=%d",
            source_url,
            len(pages_text),
            len(trimmed),
        )
        return (
            f"PDF SOURCE: {source_url}\n"
            f"EXTRACTED TEXT ({len(pages_text)} pages, {len(trimmed)} chars):\n"
            f"{'=' * 60}\n"
            f"{trimmed}"
        )
    except Exception as exc:
        logger.error("extract_pdf parse error | source=%s | error=%s", source_url, exc)
        return f"[PDF_PARSE_ERROR] Could not parse PDF content from {source_url}: {exc}"

@tool(args_schema=ExtractPDFInput)
def extract_pdf(url: str) -> str:
    """
    Download a PDF from a direct URL (e.g. an arXiv or PubMed PDF link)
    and extract its full text content for analysis.
    Use this when a research paper is only available as a PDF.
    Returns structured text with page separators.
    """
    logger.info("extract_pdf called | url=%s", url)

    try:
        response = _fetch_with_retry(url)
    except Exception as exc:
        logger.error("extract_pdf fetch failed | url=%s | error=%s", url, exc)
        return f"[PDF_FETCH_ERROR] Could not download PDF from {url}: {exc}"

    return _extract_pdf_from_bytes(response.content, source_url=url)
