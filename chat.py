import httpx
import os
import tempfile
from dotenv import load_dotenv
from groq import Groq
from colorama import Fore
import fitz  

load_dotenv()

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Try these in order — if one fails (rate limit, overloaded, etc.), fall to the next
GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it"
]

SYSTEM_PROMPT = """You are a focused document Q&A assistant. Follow these rules strictly:

1. ONLY answer based on the content of the provided document. Do not use outside knowledge unless explicitly asked to.
2. If the answer isn't in the document, say clearly: "I couldn't find that in the document." Do NOT guess or make up information.
3. Be concise and direct. No filler, no unnecessary preamble.
4. If asked to summarize, quote, or explain a section, stay strictly within what the document actually contains.
5. Remember the full conversation history provided below — stay consistent with what you've already said.
6. If the user asks something ambiguous, ask a clarifying question instead of assuming.

Never fabricate page numbers, section names, or facts not present in the document."""


def extract_text(file_path):
    try:
        text = ""
        with fitz.open(file_path) as doc:
            for page in doc:
                text += page.get_text()
        return text.strip()
    except Exception as e:
        print(f"{Fore.RED}~ Couldn't read the file: {short_error(e)}")
        return ""


def short_error(e):
    msg = str(e)
    if "429" in msg or "rate limit" in msg.lower():
        return "rate limit hit"
    if "401" in msg or ("invalid" in msg.lower() and "key" in msg.lower()):
        return "invalid API key"
    if "timeout" in msg.lower():
        return "request timed out"
    if "overloaded" in msg.lower() or "503" in msg:
        return "model overloaded"
    return msg[:80] + ("..." if len(msg) > 80 else "")


def build_context_prompt(chat_history, user_message):
    history_text = ""
    for turn in chat_history:
        history_text += f"User: {turn['user']}\nAssistant: {turn['assistant']}\n\n"

    return f"""{SYSTEM_PROMPT}

--- CONVERSATION HISTORY SO FAR ---
{history_text if history_text else "(no previous messages yet)"}

--- CURRENT QUESTION ---
User: {user_message}

Respond as the assistant, staying consistent with the conversation history above."""


def ask_groq(document_text, chat_history, user_message):
    """Tries each model in GROQ_MODELS in order until one succeeds."""
    prompt = build_context_prompt(chat_history, user_message)
    full_prompt = f"DOCUMENT CONTENT:\n{document_text[:15000]}\n\n{prompt}"

    last_error = None
    for model in GROQ_MODELS:
        try:
            response = groq_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": full_prompt}]
            )
            return response.choices[0].message.content
        except Exception as e:
            last_error = e
            print(f"{Fore.YELLOW}~ {model} unavailable ({short_error(e)}), trying next model...")
            continue

    raise last_error  # all models failed, bubble up


def chat_with_file(storage_path, athu):
    tmp_path = None
    chat_history = {}
    turn_count = 0

    try:
        response = athu.supabase.storage.from_("VOID_FILES").download(storage_path)
        ext = os.path.splitext(storage_path)[1]

        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
            tmp.write(response)
            tmp_path = tmp.name

        print(f"{Fore.CYAN}~ Reading the document...")
        document_text = extract_text(tmp_path)

        if not document_text:
            print(f"{Fore.RED}~ No readable text found in this file, can't start chat.")
            return

        print(f"{Fore.GREEN}~ You're now chatting about the file. Type 'exit' to leave the chat.\n")

        while True:
            user_input = input(f"{Fore.BLUE}You: {Fore.WHITE}").strip()

            if user_input.lower() in ("exit", "quit", "q"):
                print(f"{Fore.LIGHTMAGENTA_EX}~ Ending chat.")
                break

            if not user_input:
                continue

            history_list = list(chat_history.values())

            try:
                answer = ask_groq(document_text, history_list, user_input)
            except httpx.ConnectError:
                print(f"{Fore.RED}~ Connection lost mid-response. Check your internet and try again.")
                continue
            except Exception as e:
                print(f"{Fore.RED}~ All models failed ({short_error(e)}). Try again in a bit.")
                continue

            print(f"{Fore.YELLOW}AI: {Fore.WHITE}{answer}\n")

            turn_count += 1
            chat_history[turn_count] = {"user": user_input, "assistant": answer}

    except httpx.ConnectError:
        print(f"{Fore.RED}~ Connection lost. Check your internet and try again.")
    except Exception as e:
        print(f"{Fore.RED}~ Failed to start chat: {short_error(e)}")

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)