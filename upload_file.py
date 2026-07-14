import httpx
import mimetypes
import os
import dirNavigator
import authentication as athu
from pdf_sumariser import summarise
from colorama import Fore, Back, init
from menu_compat import TerminalMenu
from subjects import getSub

init(autoreset=True)



def edit_tags_flow(tags):
    """Lets the user optionally edit subject/category/summary. Mutates tags in place."""
    allowed_subjects = getSub()

    print(f"{Fore.LIGHTYELLOW_EX}The RECOMMENDED tags for this document are : ")
    print(f"{Fore.CYAN}SUBJECT  :  {tags[0]}")
    print(f"{Fore.CYAN}CATEGORY : {tags[1]}")
    print(f"{Fore.CYAN}SUMMARY  : {tags[2]}")

    yes_no_menu = TerminalMenu(["No", "Yes"], title="WOULD YOU LIKE TO EDIT ANY TAG ?(incase of handwritten notes)")
    if yes_no_menu.show() == 1:
        tags_menu = TerminalMenu(tags, title="Select the tag to change")
        tags_selected = tags_menu.show()

        if tags_selected == 0:
            subject = input(f"{Fore.BLUE}Enter the Subject, choose from {Fore.RED}{allowed_subjects} : ").strip()
            while subject not in allowed_subjects:
                subject = input(f"{Fore.RED}Choose again, only from (EXACT MATCH) {allowed_subjects} : ").strip()
            tags[0] = subject

        elif tags_selected == 1:
            tags[1] = input(f"{Fore.BLUE}Enter the Category : ")

        elif tags_selected == 2:
            tags[2] = input(f"{Fore.BLUE}Enter the Summary : ")

    return tags


def upload_and_sync(UUID, file_selected, tags):

    filename = os.path.basename(file_selected)
    tags[0] = tags[0].strip()
    supa_storage_path = f"{UUID}/{tags[0]}/{filename}"

    storage_uploaded = False

    try:

        content_type, _ = mimetypes.guess_type(filename)
        if content_type is None:
            content_type = "application/octet-stream"  # fallback

        with open(file_selected, "rb") as file:
            athu.supabase.storage.from_("VOID_FILES").upload(
                path=supa_storage_path,
                file=file,
                file_options={"content-type": content_type}
            )
            storage_uploaded = True




        athu.supabase.table("USERS_DATA").insert({
            "USER_ID": UUID,
            "subject": tags[0],
            "document_type": tags[1],
            "summary": tags[2],
            "storage_path": supa_storage_path
        }).execute()

        print(f"{Fore.GREEN}{Back.YELLOW}~ {filename} uploaded successfully at path {supa_storage_path}")
        return True

    except httpx.ConnectError:
        print(f"{Fore.RED}~ Connection lost mid-upload. Check your internet and try again.")
    except Exception as e:
        print(f"{Fore.RED}{Back.BLACK}Error Pushing the file ({filename}) bcuz of : {e}")

        if storage_uploaded:
            try:
                athu.supabase.storage.from_("VOID_FILES").remove([supa_storage_path])
                print(f"{Fore.YELLOW}Rolled back storage upload for {filename} to keep things in sync !")
            except Exception as rollback_error:
                print(f"{Fore.RED}{Back.BLACK}Rollback FAILED for {filename} : {rollback_error} orphaned file in storage, manual cleanup needed :(")

        return False


def upload_to_supabase(UUID):
    while True:

        try:
            file_selected = dirNavigator.navigate()
            result = summarise(file_location=file_selected)
            tags = result.split(':')
        except Exception as e:
            print(f"{Fore.RED}Failed to select/summarise file: {e}")
            continue
        tags = edit_tags_flow(tags)
        success = upload_and_sync(UUID, file_selected, tags)

        if success:
            break  
        retry_menu = TerminalMenu(["No, stop", "Yes, try another file"], title="Upload failed. Try again?")
        if retry_menu.show() != 1:
            break




