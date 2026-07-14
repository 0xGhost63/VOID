import json
from colorama import Fore, Back, init
import authentication as athu

init(autoreset=True)

TABLE = "USER_SUBJECTS"


def _normalize(raw) -> list:
    """Strip, UPPERCASE, dedupe — matches VOID Web behaviour."""
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return [raw.strip().upper()] if raw.strip() else []
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        s = str(item).strip().upper()
        if s and s not in out:
            out.append(s)
    return out


def _friendly_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if "name resolution" in msg or "errno -3" in msg or "nodename nor servname" in msg:
        return "No internet connection — check your network and try again."
    if "connection refused" in msg or "errno 111" in msg:
        return "Could not reach the server. Please try again in a moment."
    if "timed out" in msg or "timeout" in msg:
        return "Request timed out. Check your connection and try again."
    if "network is unreachable" in msg or "errno 101" in msg:
        return "Network unreachable. Check your internet connection."
    if "USER_SUBJECTS" in str(exc) or "schema cache" in msg or "does not exist" in msg:
        return f"USER_SUBJECTS table issue: {exc}"
    return str(exc)


def get_subjects(uuid: str):

    if not uuid:
        return [], "Not authenticated"
    try:
        response = (
            athu.supabase.table(TABLE)
            .select("subjects")
            .eq("USER_ID", uuid)
            .limit(1)
            .execute()
        )
        if not response.data:
            return [], None
        return _normalize(response.data[0].get("subjects")), None
    except Exception as e:
        msg = _friendly_error(e)
        print(f"{Fore.RED}{Back.BLACK}Failed to load subjects: {msg}")
        return [], msg


def set_subjects(uuid: str, subjects: list):

    if not uuid:
        msg = "Not authenticated — cannot save subjects."
        print(f"{Fore.RED}{Back.BLACK}{msg}")
        return False, msg
    try:
        cleaned = _normalize(subjects)
        athu.supabase.table(TABLE).upsert(
            {
                "USER_ID": uuid,
                "subjects": cleaned,
            },
            on_conflict="USER_ID",
        ).execute()
        return True, None
    except Exception as e:
        msg = _friendly_error(e)
        print(f"{Fore.RED}{Back.BLACK}Failed to save subjects: {msg}")
        return False, msg


def change_subjects(uuid: str) -> bool:
    print(
        f"{Fore.RED}{Back.BLACK}ENTER THE SUBJECTS YOU ARE CURRENTLY ENROLLED IN "
        f"(ONE-TIME SETUP),enter 'exit' or 'quit' to end : "
    )
    counter = 1
    subjects = []
    quit_options = ["EXIT", "QUIT", "Q", "E"]
    while True:
        temp = input(f"{Fore.LIGHTBLUE_EX}Enter the subject # {counter} : ").strip().upper()
        if temp in quit_options:
            break
        if temp and temp not in subjects:
            subjects.append(temp)
            counter += 1

    if not subjects:
        print(f"{Fore.YELLOW}No subjects entered. Please add at least one subject.")
        return False

    ok, _err = set_subjects(uuid, subjects)
    if ok:
        print(f"{Fore.GREEN}DONE WITH THE CONFIGURATIONS !")
        return True
    return False
