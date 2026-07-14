from colorama import Fore, init
from subjects_service import get_subjects, change_subjects

init(autoreset=True)

everything_ok = False


def configuration_check(uuid: str):
    """
    After login: load subjects from USER_SUBJECTS for this UUID.
    Empty list → interactive setup (upsert to Supabase).
    Non-empty → good to go. No subjects.py disk check.
    """
    global everything_ok

    if not uuid:
        print(f"{Fore.RED}Not authenticated — cannot check subjects.")
        everything_ok = False
        return False

    subjects, err = get_subjects(uuid)
    if err:
        print(f"{Fore.RED}Failed to load subjects configuration: {err}")
        everything_ok = False
        return False

    if subjects:
        print(f"{Fore.GREEN}Good to go !")
        everything_ok = True
        return everything_ok

    ok = change_subjects(uuid)
    everything_ok = ok
    return ok
