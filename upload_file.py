import os

import dirNavigator
import authentication as athu
import library
from pdf_sumariser import summarise
from colorama import Fore, Back, init
from menu_compat import TerminalMenu
from subjects_service import get_subjects

init(autoreset=True)


def edit_tags_flow(tags, allowed_subjects):
    """Lets the user optionally edit subject/category/summary. Mutates tags in place."""
    print(f"{Fore.LIGHTYELLOW_EX}The RECOMMENDED tags for this document are : ")
    print(f"{Fore.CYAN}SUBJECT  :  {tags[0]}")
    print(f"{Fore.CYAN}CATEGORY :  {tags[1]}")
    print(f"{Fore.CYAN}SUMMARY  :  {tags[2]}")

    yes_no_menu = TerminalMenu(
        ["No", "Yes"],
        title="WOULD YOU LIKE TO EDIT ANY TAG ?(incase of handwritten notes)",
    )
    if yes_no_menu.show() == 1:
        tags_menu = TerminalMenu(tags, title="Select the tag to change")
        tags_selected = tags_menu.show()

        if tags_selected == 0:
            subject = input(
                f"{Fore.BLUE}Enter the Subject, choose from {Fore.RED}{allowed_subjects} : "
            ).strip().upper()
            while subject not in allowed_subjects:
                subject = input(
                    f"{Fore.RED}Choose again, only from (EXACT MATCH) {allowed_subjects} : "
                ).strip().upper()
            tags[0] = subject

        elif tags_selected == 1:
            tags[1] = input(f"{Fore.BLUE}Enter the Category : ")

        elif tags_selected == 2:
            tags[2] = input(f"{Fore.BLUE}Enter the Summary : ")

    return tags


def upload_and_sync(UUID, file_selected, tags):
    """Store the file in every connected place (VOID Cloud + optional local folder)."""
    try:
        _doc_id, places, errors = library.for_user(UUID).import_file(
            file_path=file_selected,
            subject=tags[0],
            doc_type=tags[1],
            summary=tags[2],
        )
    except Exception as exc:
        print(
            f"{Fore.RED}{Back.BLACK}Error storing the file "
            f"({os.path.basename(file_selected)}) because of : {exc}"
        )
        return False

    filename = os.path.basename(file_selected)
    stored = 0
    for result in places:
        kind, path = result[0], result[1]
        status = result[2] if len(result) > 2 else "ok"
        label = {
            "cloud": "VOID Cloud",
            "local": "Local folder",
            "gdrive": "Google Drive",
            "github": "GitHub",
        }.get(kind, kind)
        if status == "ok":
            stored += 1
            print(f"{Fore.GREEN}~ {filename} → {label} ({path})")
        else:
            print(
                f"{Fore.YELLOW}~ {filename} → {label} queued until it is reachable "
                f"({path})"
            )
    for error in errors:
        print(f"{Fore.YELLOW}~ Couldn't reach {error}")

    if not stored:
        print(
            f"{Fore.RED}~ File was not stored anywhere yet. "
            "It will be retried automatically on the next sync."
        )
        return False
    return True


def upload_to_supabase(UUID):
    while True:
        try:
            allowed_subjects, err = get_subjects(UUID)
            if err:
                print(f"{Fore.RED}Cannot upload without subjects: {err}")
                return
            if not allowed_subjects:
                print(f"{Fore.RED}No subjects configured. Set them in Settings first.")
                return

            file_selected = dirNavigator.navigate()
            if not file_selected:
                print(f"{Fore.LIGHTMAGENTA_EX}No file selected. Retreating...")
                return
            result = summarise(
                file_location=file_selected,
                authorized_subjects=allowed_subjects,
                access_token=athu.ACCESS_TOKEN,
            )
            tags = [part.strip() for part in result.split(":", 2)]
            while len(tags) < 3:
                tags.append("")
        except Exception as exc:
            print(f"{Fore.RED}Failed to select/summarise file: {exc}")
            continue

        tags = edit_tags_flow(tags, allowed_subjects)
        success = upload_and_sync(UUID, file_selected, tags)

        if success:
            break
        retry_menu = TerminalMenu(
            ["No, stop", "Yes, try another file"], title="Upload failed. Try again?"
        )
        if retry_menu.show() != 1:
            break
