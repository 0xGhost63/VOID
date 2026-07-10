import os
import time
import base64
import requests
import fitz  # PyMuPDF — pip install pymupdf
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
        return f"""You are an expert information extraction assistant specialized in university academic documents. Your goal is to analyze the first page text of an academic document and extract the subject, assessment type/number, and a razor-sharp summary.

CRITICAL INSTRUCTION: The input document can be an Assignment, a Quiz, Lecture Notes, or a Textbook chapter/excerpt. You must dynamically adapt your logic based on the text indicators.

STEP 1 — IDENTIFY THE TYPE AND NUMBER / REFERENCE:
Analyze the header and metadata lines to determine what type of document this is and its numerical identifier:
1. ASSIGNMENTS / LABS: Look for "Assignment #", "Lab #", "Assignment No", or "Lab Task". Extract the number. If "Lab" is explicitly mentioned anywhere near the assignment label, mark it as "Lab [Number]". Otherwise, default it to "Theory [Number]" (e.g., "Assignment # 02" becomes "Theory 02").
2. QUIZZES: Look for "Quiz #", "Quiz No", or "Class Test". Extract the number and mark it as "Quiz [Number]" (e.g., "Quiz 03").
3. LECTURE NOTES / SLIDES: Look for keywords like "Lecture #", "Week #", "Slide", "Topic", or "Handout". Extract the number/week if present and mark it as "Notes [Number/Week]" (e.g., "Notes 05" or "Notes Week 04"). If no number is found, use "Notes".
4. BOOKS / TEXTBOOKS: Look for "Chapter #", "Ch #", "Section", or textbook title patterns. Extract the chapter number and mark it as "Book Ch [Number]" (e.g., "Book Ch 04"). If it's a general book excerpt without a clear chapter, use "Book".

If absolutely no type or number can be inferred from the context, leave this field completely blank.

STEP 2 — MAP THE SUBJECT:
Look for indicators like "Course:", "Subject:", "Class:", or department codes (e.g., CSC-211, hum-102). 
Match that detected course name or code to the closest abbreviation/entry in this authorized subject list: {subject_list}
- Use advanced semantic judgment to map full or partial names to their common abbreviations in the list (e.g., "Data Structures and Algorithms" or "CSC-211" -> "DSA"; "Object Oriented Programming" -> "OOP"; "Digital Logic Design" -> "DLD"; "Linear Algebra" -> "LA").
- If the subject list contains a literal matching abbreviation, prioritize it.
- Only leave this field completely blank if there is absolutely no subject name, code, or context clue available.

STEP 3 — GENERATE THE SUMMARY:
Synthesize the primary focus of the document into a single, high-density phrase.
- Max limit: 7-8 words.
- For Assignments/Quizzes: Describe what the task implements, solves, or tests (e.g., "Implements event registration using linked lists").
- For Notes/Books: Describe the core theoretical concept or topic covered (e.g., "Explains memory management and paging mechanisms").

OUTPUT FORMAT:
Return ONLY plain text. Absolutely NO markdown formatting, NO backticks, NO quotes, NO conversational filler, and NO reasoning process. Output exactly one line matching this schema:

SUBJECT : TYPE NUMBER : SUMMARY

Rules for separators:
- Keep both ":" characters exactly as shown, even if a field is entirely blank (e.g., "DSA : : Summary here" or " : Notes 02 : Summary here").

EXAMPLES FOR DECISION MAKING:
- Input: "Lab Assignment # 02... Course: Data Structures..." 
  Output: DSA : Lab 02 : Implements event registration using linked lists
- Input: "Quiz # 3... Subject: Object Oriented Programming..." 
  Output: OOP : Quiz 03 : Tests polymorphism and inheritance concepts
- Input: "Lecture 5: Memory Management... Operating Systems..." 
  Output: OS : Notes 05 : Explains paging and virtual memory allocation
- Input: "Chapter 4: Vector Spaces... Linear Algebra Textbook..." 
  Output: LA : Book Ch 04 : Covers vector spaces and subspaces properties

DOCUMENT TEXT (FIRST PAGE):
\"\"\"
{pdf_text}
\"\"\"

Now analyze and output the single structured line:"""

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
                        f"{Fore.YELLOW}[!] {model} rate-limited, retrying in {RETRY_DELAY_SECONDS}s "
                        f"(attempt {attempt}/{RETRY_ATTEMPTS})..."
                    )
                    time.sleep(RETRY_DELAY_SECONDS)
                    continue
                print(
                    f"{Fore.YELLOW}[!] {model} failed ({e}), moving to next model..."
                )
                break
            except Exception as e:
                last_error = e
                print(
                    f"{Fore.YELLOW}[!] {model} failed ({e}), moving to next model..."
                )
                break

    raise RuntimeError(
        f"All models in fallback chain failed. Last error: {last_error}"
    )