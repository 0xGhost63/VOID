import httpx
import os
import tempfile
import requests
from colorama import Fore
import fitz

API_BASE = os.getenv("VOID_API_BASE", "https://0xghost-void.vercel.app").rstrip("/")


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
    if "401" in msg:
        return "session expired, please log in again"
    if "timeout" in msg.lower():
        return "request timed out"
    if "overloaded" in msg.lower() or "503" in msg:
        return "model overloaded"
    return msg[:80] + ("..." if len(msg) > 80 else "")


def ask_backend(document_text, chat_history, user_message, access_token):
    """Sends the question + document + history to the VOID backend (holds the Groq key)."""
    payload = {
        "document_text": document_text[:15000],
        "chat_history": chat_history,
        "message": user_message,
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.post(
        f"{API_BASE}/api/cli/chat",
        json=payload,
        headers=headers,
        timeout=45,
    )
    resp.raise_for_status()
    return resp.json()["answer"]


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
                answer = ask_backend(
                    document_text, history_list, user_input, athu.ACCESS_TOKEN
                )
            except httpx.ConnectError:
                print(f"{Fore.RED}~ Connection lost mid-response. Check your internet and try again.")
                continue
            except requests.exceptions.RequestException as e:
                print(f"{Fore.RED}~ Couldn't reach the AI service ({short_error(e)}). Try again in a bit.")
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
