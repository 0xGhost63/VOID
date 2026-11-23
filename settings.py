######## TO BE COMPLETED LATER
# -PASSWORDS
# -CLOUD MANAGEMENT etc...

import os

from subjects_service import change_subjects, get_subjects
from menu_compat import TerminalMenu
from colorama import Fore, Back, init

init(autoreset=True)


### change the subjects
def change_user_subjects(uuid: str):
    yes_no = ["YES", "NO"]
    yes_no_menu = TerminalMenu(yes_no, title="Are you sure to change the subjects ? ")
    yes_no_selected = yes_no_menu.show()

    if yes_no_selected == 1:
        print(f"{Fore.LIGHTMAGENTA_EX}Retreating.... :)")
        return
    else:
        if not change_subjects(uuid):
            print(f"{Fore.RED}Could not update subjects. Try again later.")
            return
        print(f"{Fore.GREEN}Done changing the subjects")
        subjects, err = get_subjects(uuid)
        if err:
            print(f"{Fore.RED}Saved, but failed to re-load subjects: {err}")
            return
        print(f"{Fore.BLUE}Your new subjects are : ")
        for subject in subjects:
            print(f"{Fore.CYAN}~ {subject}")


# $$$$$$$ storage $$$$$$$ #

def _print_places(lib):
    print(f"{Fore.CYAN}Connected places :")
    for place in lib.status():
        if place["connected"]:
            print(f"  {Fore.GREEN}● {place['name']:<14} {place['detail']}")
        else:
            print(f"  {Fore.YELLOW}○ {place['name']:<14} {place['detail']}")


def _offer_sync(lib):
    choice = TerminalMenu(
        ["No", "Yes"],
        title="Copy your existing VOID files into this place now?",
    ).show()
    if choice == 1:
        print(f"{Fore.CYAN}~ Syncing... (this can take a minute)")
        lib.sync(quiet=False)
        print(f"{Fore.GREEN}~ Sync complete.")


def _add_local_folder(uuid: str):
    import library
    import storage_config

    default = os.path.join(os.path.expanduser("~"), "VOID")
    root = input(f"{Fore.BLUE}Folder path [{default}] : ").strip() or default
    try:
        root = storage_config.set_local_place(root)
    except Exception as exc:
        print(f"{Fore.RED}Couldn't use that folder: {exc}")
        return

    lib = library.for_user(uuid)
    lib.reload()
    print(f"{Fore.GREEN}~ Local folder connected: {root}")

    copy_now = TerminalMenu(
        ["No", "Yes"],
        title="Copy your existing VOID files into this folder now?",
    ).show()
    if copy_now == 1:
        print(f"{Fore.CYAN}~ Copying... (this can take a minute)")
        copied, errors = lib.mirror_all_to_local(
            progress=lambda count, title: print(
                f"{Fore.GREEN}  + {title} ({count})"
            )
        )
        print(f"{Fore.GREEN}~ Copied {copied} file(s).")
        for error in errors:
            print(f"{Fore.YELLOW}  ! {error}")


def _remove_local_folder(uuid: str):
    import library
    import storage_config

    confirm = TerminalMenu(
        ["No", "Yes"],
        title="Disconnect the local folder? Files on disk are NOT deleted.",
    ).show()
    if confirm != 1:
        print(f"{Fore.LIGHTMAGENTA_EX}Retreating.... :)")
        return

    storage_config.remove_local_place()
    library.for_user(uuid).reload()
    print(f"{Fore.GREEN}~ Local folder disconnected. Your files are still on disk.")


# ----------------------------------------------------------------------
# GitHub
# ----------------------------------------------------------------------
def _connect_github(uuid: str):
    import library
    import storage_config

    print(
        f"{Fore.CYAN}Create a fine-grained PAT with Contents: Read and write "
        "on one repository.\n"
        f"{Fore.CYAN}For a small repo, Contents: Read and write is enough."
    )
    token = (
        os.getenv("VOID_GITHUB_TOKEN")
        or input(f"{Fore.BLUE}GitHub token : ").strip()
    )
    repo = input(f"{Fore.BLUE}Repository (owner/name) : ").strip()
    branch = (
        input(f"{Fore.BLUE}Branch [main] : ").strip() or "main"
    )
    root = (
        input(f"{Fore.BLUE}Folder in the repo [VOID] : ").strip() or "VOID"
    )

    if not token or "/" not in repo:
        print(f"{Fore.RED}~ Need a token and a repository in owner/name form.")
        return

    storage_config.set_github_place(token, repo, branch, root)
    lib = library.for_user(uuid)
    lib.reload()

    if lib.github is None:
        print(f"{Fore.RED}~ GitHub is still not configured.")
        return

    try:
        lib.github.test()
    except Exception as exc:
        print(f"{Fore.RED}~ GitHub connection failed: {exc}")
        print(
            f"{Fore.YELLOW}~ Config saved. Fix the token/repo, or "
            "choose DISCONNECT GITHUB to remove it."
        )
        return

    print(f"{Fore.GREEN}~ GitHub connected: {lib.github.describe()}")
    _offer_sync(lib)


def _disconnect_github(uuid: str):
    import library
    import storage_config

    confirm = TerminalMenu(
        ["No", "Yes"],
        title="Disconnect GitHub? Files in the repository are NOT deleted.",
    ).show()
    if confirm != 1:
        print(f"{Fore.LIGHTMAGENTA_EX}Retreating.... :)")
        return
    storage_config.remove_github_place()
    library.for_user(uuid).reload()
    print(f"{Fore.GREEN}~ GitHub disconnected. Your files are still in the repo.")


# ----------------------------------------------------------------------
# Google Drive
# ----------------------------------------------------------------------
def _connect_gdrive(uuid: str):
    import library
    import storage_config
    from sources.gdrive import GoogleDriveProvider

    client_id = os.getenv("VOID_GDRIVE_CLIENT_ID") or input(
        f"{Fore.BLUE}Google OAuth client id "
        "(TVs and Limited Input devices) : "
    ).strip()
    if not client_id:
        print(
            f"{Fore.RED}~ Google Drive needs an OAuth client id.\n"
            f"{Fore.YELLOW}  Create one at Google Cloud Console → APIs & Services "
            "→ Credentials → OAuth client ID → TVs and Limited Input devices.\n"
            f"{Fore.YELLOW}  Enable the Google Drive API, then try again."
        )
        return

    client_secret = os.getenv("VOID_GDRIVE_CLIENT_SECRET") or input(
        f"{Fore.BLUE}Google OAuth client secret (optional) : "
    ).strip()
    folder_name = os.getenv("VOID_GDRIVE_FOLDER", "VOID") or "VOID"

    refresh_token = os.getenv("VOID_GDRIVE_REFRESH_TOKEN")
    folder_id = os.getenv("VOID_GDRIVE_FOLDER_ID")

    try:
        if refresh_token:
            provider = GoogleDriveProvider(
                {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "folder_id": folder_id or "root",
                }
            )
            if not folder_id:
                folder_id = provider.ensure_folder(folder_name)
            config = {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "folder_id": folder_id,
            }
        else:
            from sources.gdrive_auth import connect as gdrive_connect

            config = gdrive_connect(client_id, client_secret, folder_name)
    except Exception as exc:
        print(f"{Fore.RED}~ Google Drive connection failed: {exc}")
        return

    storage_config.set_gdrive_place(
        config["client_id"],
        config["client_secret"],
        config["refresh_token"],
        config["folder_id"],
    )
    lib = library.for_user(uuid)
    lib.reload()

    if lib.gdrive is None:
        print(f"{Fore.RED}~ Google Drive is still not configured.")
        return

    try:
        lib.gdrive.test()
    except Exception as exc:
        print(f"{Fore.RED}~ Google Drive check failed: {exc}")
        return

    print(f"{Fore.GREEN}~ Google Drive connected: {lib.gdrive.describe()}")
    _offer_sync(lib)


def _disconnect_gdrive(uuid: str):
    import library
    import storage_config

    confirm = TerminalMenu(
        ["No", "Yes"],
        title="Disconnect Google Drive? Files in Drive are NOT deleted.",
    ).show()
    if confirm != 1:
        print(f"{Fore.LIGHTMAGENTA_EX}Retreating.... :)")
        return
    storage_config.remove_gdrive_place()
    library.for_user(uuid).reload()
    print(f"{Fore.GREEN}~ Google Drive disconnected. Your files are still in Drive.")


def storage_menu(uuid: str):
    import library

    lib = library.for_user(uuid)

    while True:
        line = f"{Fore.LIGHTYELLOW_EX}" + "-" * 60
        print(line)
        _print_places(lib)
        print(line)

        options = ["EXIT STORAGE", "SYNC NOW"]

        if lib.local is None:
            options.append("ADD LOCAL FOLDER")
        else:
            options.append("CHANGE LOCAL FOLDER")
            options.append("REMOVE LOCAL FOLDER")
            options.append("COPY EXISTING FILES TO LOCAL FOLDER")

        if lib.github is None:
            options.append("CONNECT GITHUB")
        else:
            options.append("DISCONNECT GITHUB")

        if lib.gdrive is None:
            options.append("CONNECT GOOGLE DRIVE")
        else:
            options.append("DISCONNECT GOOGLE DRIVE")

        selected = TerminalMenu(options, title="STORAGE").show()
        if selected is None or selected == 0:
            print(f"{Fore.CYAN}Retreating... :)")
            return

        action = options[selected]
        if action == "SYNC NOW":
            print(f"{Fore.CYAN}~ Syncing...")
            lib.sync(quiet=False)
            print(f"{Fore.GREEN}~ Sync complete.")
        elif action in ("ADD LOCAL FOLDER", "CHANGE LOCAL FOLDER"):
            _add_local_folder(uuid)
        elif action == "REMOVE LOCAL FOLDER":
            _remove_local_folder(uuid)
        elif action == "COPY EXISTING FILES TO LOCAL FOLDER":
            print(f"{Fore.CYAN}~ Copying... (this can take a minute)")
            copied, errors = lib.mirror_all_to_local(
                progress=lambda count, title: print(
                    f"{Fore.GREEN}  + {title} ({count})"
                )
            )
            print(f"{Fore.GREEN}~ Copied {copied} file(s).")
            for error in errors:
                print(f"{Fore.YELLOW}  ! {error}")
        elif action == "CONNECT GITHUB":
            _connect_github(uuid)
        elif action == "DISCONNECT GITHUB":
            _disconnect_github(uuid)
        elif action == "CONNECT GOOGLE DRIVE":
            _connect_gdrive(uuid)
        elif action == "DISCONNECT GOOGLE DRIVE":
            _disconnect_gdrive(uuid)


# $$$$$$$ settings options $$$$$$$ #

def settings_menu(uuid: str):
    while True:
        settings_list = ["EXIT SETTINGS", "CHANGE SUBJECTS", "STORAGE"]
        settings_Menu = TerminalMenu(settings_list, title="CHOOSE THE SETTINGS OPTION")
        settings_selected = settings_Menu.show()

        if settings_selected is None:
            continue
        elif settings_selected == 0:
            print(f"{Fore.CYAN}Retreating... :)")
            break
        elif settings_selected == 1:
            change_user_subjects(uuid)
        elif settings_selected == 2:
            storage_menu(uuid)
