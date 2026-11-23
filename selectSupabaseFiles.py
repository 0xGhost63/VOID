from colorama import Fore, init

import library
from menu_compat import TerminalMenu

init(autoreset=True)


def selectDirectory(UUID):
    """List subjects from the unified catalog (cloud + local)."""
    lib = library.for_user(UUID)
    dirs = lib.subjects()
    if not dirs:
        print(f"{Fore.YELLOW}~ No files yet. Upload something first.")
        return None

    menu = TerminalMenu(["GO BACK"] + dirs, title="SELECT A SUBJECT")
    selected = menu.show()
    if selected is None or selected == 0:
        print(f"{Fore.LIGHTMAGENTA_EX}Retreating...")
        return None

    subject = dirs[selected - 1]
    print(f"{Fore.BLUE}You selected {subject}")
    return subject


def selectFile(directory, UUID):
    """List files for a subject, with a small badge for where copies live."""
    lib = library.for_user(UUID)
    documents = lib.list_documents(directory)
    if not documents:
        print(f"{Fore.YELLOW}~ No files in {directory}.")
        return None

    labels = []
    for document in documents:
        doc_type = (document.get("doc_type") or "FILE").strip()
        summary = (document.get("summary") or document.get("title") or "").strip()
        places = " ".join(f"[{place}]" for place in document.get("places", []))
        labels.append(f"{doc_type[:18].ljust(18)} │ {summary}  {places}")

    menu = TerminalMenu(labels, title="Select The File")
    selected = menu.show()
    if selected is None:
        return None

    print(f"{Fore.BLUE}You selected {labels[selected]}...")
    return documents[selected]
