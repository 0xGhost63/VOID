import os
import time
import base64
import requests
import fitz  
from dotenv import load_dotenv
from colorama import init, Fore, Back
import subjects


def summarise(file_location: str) -> str:
    """
    Extracts content from the first page of an academic document,
    infers the subject and document metadata using Groq API.
    If the document has handwritten or scanned text (no text extracted),
    it falls back to sending the raw PDF directly to the Gemini API.
    """
    init(autoreset=True)
    load_dotenv()

    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

    MODEL_CHAIN = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
    ]

    RETRY_ATTEMPTS = 2
    RETRY_DELAY_SECONDS = 2
    MAX_CHARS = 3000

    def extract_pdf_text(path: str) -> str:
        doc = fitz.open(path)
        first_page_text = doc[0].get_text()
        doc.close()
        return first_page_text.strip()[:MAX_CHARS]

    def build_prompt(pdf_text: str) -> str:
        subject_list = subjects.getSub()
        return f"""You are an expert at classifying university academic documents (assignment, quiz, notes, or book) and extracting a short summary.

DOCUMENT TEXT (FIRST PAGE):
\"\"\"
{pdf_text}
\"\"\"

AUTHORIZED SUBJECT LIST (closed set — you may ONLY output values from this exact list, copied character-for-character):
{subject_list}

Follow these steps in order.

STEP 1 — DETERMINE SUBJECT (MANDATORY — NEVER BLANK, NEVER INVENTED):
- Look for explicit signals first: "Course:", "Subject:", "Class:", a department code (e.g. CSC-211, HUM-102), or the subject name mentioned anywhere in the header/title.
- Use semantic judgment to map that signal to the closest matching entry in the AUTHORIZED SUBJECT LIST (e.g. "Data Structures and Algorithms" / "CSC-211" -> "DSA"; "Object Oriented Programming" -> "OOP"; "Digital Logic Design" -> "DLD"; "Linear Algebra" -> "LA").
- If there is NO explicit signal, infer the subject from the CONTENT ITSELF (code style, terminology, topic domain, syntax, formulas, diagrams etc.) and match that inferred domain to the closest entry in the list. Example: unlabeled code using nodes/pointers/traversal -> DSA. Unlabeled content about transistors/logic gates -> DLD.
- You MUST always output the single closest matching entry from the AUTHORIZED SUBJECT LIST — copied EXACTLY as it appears there (same spelling, case, punctuation, abbreviation). Never paraphrase it, never invent a new abbreviation, never output a subject not present in the list.
- There is no valid scenario where this field is blank. Even weak or indirect signals are enough to make a best-fit decision — you must always commit to the single closest match.

STEP 2 — DETERMINE TYPE (MANDATORY — NEVER BLANK). Check in this priority order and stop at the first match:

  a) ASSIGNMENT/LAB — text contains "Assignment #", "Assignment No", "Lab #", or "Lab Task".
     - If "Lab" appears near the label -> "Lab [Number]"
     - Otherwise -> "Theory Assignment [Number]"

  b) QUIZ — text contains "Quiz #", "Quiz No", or "Class Test".
     -> "Quiz [Number]"

  c) BOOK — text contains "Chapter #", "Ch #", "Section #", or clear textbook title/formatting.
     - If chapter number found -> "Book Ch [Number]"
     - Otherwise -> "Book"

  d) NOTES — MANDATORY FALLBACK. If none of a/b/c match, you MUST use this. This covers lecture slides, week/topic handouts, code snippets, short excerpts, or any text with no clear assignment/quiz/book label.
     - If a lecture/week number is present -> "Notes [Number]"
     - Otherwise -> "Notes"

Every document matches one of a/b/c/d. There is no valid case where TYPE is blank.

STEP 3 — SUMMARY (max 7-8 words, MANDATORY, never blank):
- Assignments/Quizzes: what it implements/solves/tests.
- Notes/Books: the core concept covered.

OUTPUT — exactly one line, no markdown, no quotes, no extra commentary. ALL THREE FIELDS MUST BE FILLED — THIS IS THE HIGHEST PRIORITY RULE:
SUBJECT : TYPE NUMBER : SUMMARY

EXAMPLES:
Input: "Lab Assignment # 02... Course: Data Structures..."
Output: DSA : Lab 02 : Implements event registration using linked lists

Input: "Quiz # 3... Subject: Object Oriented Programming..."
Output: OOP : Quiz 03 : Tests polymorphism and inheritance concepts

Input: "Lecture 5: Memory Management... Operating Systems..."
Output: OS : Notes 05 : Explains paging and virtual memory allocation

Input: "Chapter 4: Vector Spaces... Linear Algebra Textbook..."
Output: LA : Book Ch 04 : Covers vector spaces and subspaces properties

Input: a two-page excerpt with no header, just code + a short explanation of stack push/pop, no course mentioned
Output: DSA : Notes : Explains stack push and pop implementation

Now output the single structured line for the document above."""

    def extract_summary_line(text: str) -> str:
        lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
        candidates = [l for l in lines if l.count(":") >= 2]
        if candidates:
            return candidates[-1]
        return lines[-1] if lines else text.strip()

    def call_model(model: str, prompt: str, headers: dict) -> str:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 100,
        }
        resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

    def call_gemini_vision(path: str, base_prompt: str) -> str:
        """Fallback to handle image/handwritten PDFs natively using Gemini."""
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is missing from environment variables.")
        
        print(f"{Fore.CYAN}[*] No selectable text found. Uploading raw PDF file to Gemini for multimodal analysis...")
        
        with open(path, "rb") as f:
            pdf_bytes = f.read()
        pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
        
        payload = {
            "contents": [{
                "parts": [
                    {
                        "inlineData": {
                            "mimeType": "application/pdf",
                            "data": pdf_b64
                        }
                    },
                    {
                        "text": base_prompt
                    }
                ]
            }],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 100
            }
        }
        
        headers = {"Content-Type": "application/json"}
        resp = requests.post(gemini_url, headers=headers, json=payload, timeout=45)
        resp.raise_for_status()
        data = resp.json()
        
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()

    # Core Execution
    pdf_text = extract_pdf_text(file_location)
    
    # Check if text extraction yielded virtually nothing (likely a scan or handwritten text)
    if len(pdf_text) < 5:
        try:
            # Re-build prompt passing a placeholder string since the model will view the actual document data directly
            prompt = build_prompt("[Handwritten or Scanned Document Provided Directly in Context]")
            raw_text = call_gemini_vision(file_location, prompt)
            summary_result = extract_summary_line(raw_text)
            print(f"\nOutput (Gemini Fallback) : {Fore.GREEN}{Back.BLACK}{summary_result}")
            return summary_result
        except Exception as gemini_err:
            raise RuntimeError(f"Text extraction failed and Gemini fallback failed: {gemini_err}")

    # Standard textual pipeline via Groq
    prompt = build_prompt(pdf_text)
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    last_error = None

    for model in MODEL_CHAIN:
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                raw_text = call_model(model, prompt, headers)
                summary_result = extract_summary_line(raw_text)

                # print(f"\nOutput : {Fore.GREEN}{Back.BLACK}{summary_result}")
                return summary_result

            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else None
                last_error = e
                if status == 429 and attempt < RETRY_ATTEMPTS:
                    print(
                        f"{Fore.YELLOW}[!] Summarizer error, retrying in {RETRY_DELAY_SECONDS}s "
                        f"(attempt {attempt}/{RETRY_ATTEMPTS})..."
                    )
                    time.sleep(RETRY_DELAY_SECONDS)
                    continue
                print(
                    f"{Fore.YELLOW}[!] Summarizer failed ({e}), moving to next fallback..."
                )
                break
            except Exception as e:
                last_error = e
                print(
                    f"{Fore.YELLOW}[!] Summarizerfailed ({e}), moving to fallback..."
                )
                break

    raise RuntimeError(
        f"All summarizers in fallback chain failed :( Last error: {last_error}"
    )