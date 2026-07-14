import os
import base64
import requests
import fitz
from colorama import init, Fore, Back

# Public VOID Web deployment — holds Groq/Gemini keys server-side
API_BASE = os.getenv("VOID_API_BASE", "https://0xghost-void.vercel.app").rstrip("/")


def summarise(file_location: str, authorized_subjects: list, access_token: str) -> str:
    """
    Extracts content from the first page of an academic document,
    then asks the VOID backend to infer subject / type / summary.
    Scanned or handwritten PDFs (no extractable text) use the vision route.
    """
    init(autoreset=True)

    if not authorized_subjects:
        raise ValueError("No authorized subjects provided — configure subjects first.")
    if not access_token:
        raise ValueError("Not authenticated — missing access token. Please log in again.")

    MAX_CHARS = 3000

    def extract_pdf_text(path: str) -> str:
        doc = fitz.open(path)
        first_page_text = doc[0].get_text()
        doc.close()
        return first_page_text.strip()[:MAX_CHARS]

    def extract_summary_line(text: str) -> str:
        lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
        candidates = [l for l in lines if l.count(":") >= 2]
        if candidates:
            return candidates[-1]
        return lines[-1] if lines else text.strip()

    headers = {"Authorization": f"Bearer {access_token}"}
    subject_list = list(authorized_subjects)
    pdf_text = extract_pdf_text(file_location)

    # Scanned / handwritten -> vision fallback on the backend
    if len(pdf_text) < 5:
        print(f"{Fore.CYAN}[*] No selectable text found. Sending file for AI analysis...")
        try:
            with open(file_location, "rb") as f:
                pdf_b64 = base64.b64encode(f.read()).decode("utf-8")

            resp = requests.post(
                f"{API_BASE}/api/cli/summarize-scanned",
                json={"pdf_base64": pdf_b64, "subject_list": subject_list},
                headers=headers,
                timeout=60,
            )
            resp.raise_for_status()
            summary_result = extract_summary_line(resp.json()["result"])
            print(f"\nOutput (Vision Fallback) : {Fore.GREEN}{Back.BLACK}{summary_result}")
            return summary_result
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            if status == 401:
                raise RuntimeError("Session expired. Please log out and log back in.")
            raise RuntimeError(f"Vision fallback failed: {e}")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Couldn't reach the AI service: {e}")

    # Standard textual pipeline via backend
    try:
        resp = requests.post(
            f"{API_BASE}/api/cli/summarize",
            json={"pdf_text": pdf_text, "subject_list": subject_list},
            headers=headers,
            timeout=45,
        )
        resp.raise_for_status()
        return extract_summary_line(resp.json()["result"])

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else None
        if status == 401:
            raise RuntimeError("Session expired. Please log out and log back in.")
        raise RuntimeError(f"Summarizer failed: {e}")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Couldn't reach the AI service: {e}")
