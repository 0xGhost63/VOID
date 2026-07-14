from colorama import Fore, Back, init
from menu_compat import TerminalMenu
import authentication as athu

init(autoreset=True)

def selectDirectory(UUID):

    ###SELECTING THE FOLDER/SUBJECT

    try:
        response = athu.supabase.rpc("get_distinct_subjects", {"uid": UUID}).execute()
        dirs = [row["subject"] for row in response.data]
        dirs.insert(0,"GO BACK")
    
    except Exception as e:
        print (f"Error while getting directories : {e}")

    try:
        dir_menu=TerminalMenu(dirs,title="SELECT A SUBJECT")
        dir_selcted=dir_menu.show()
        print(f"{Fore.BLUE}You Selected {dirs[dir_selcted]} ")

    except Exception as e:
        print(f"{Fore.RED}No subjects found (or failed to fetch directory list).")
        return

    if dir_selcted==0:
        print(f"{Fore.LIGHTMAGENTA_EX}Retreating...")
        return 
    
    else :
        return dirs[dir_selcted]


def selectFile(directory,UUID):
    
    try:
        response = athu.supabase.table("USERS_DATA").select("*").eq("USER_ID", UUID).eq("subject",directory).execute()
        data = response.data

        files_list=[]

        for da in data:
            files_list.append(f"{da['document_type'].strip().ljust(22)}│  {da['summary']}")
        files_menu=TerminalMenu(files_list,title="Select The File")
        file_selected = files_menu.show()

        print(f"You selected the file {files_list[file_selected]}...")

        return data[file_selected]

        
    except Exception as e:
        print(f"Error while accessing the file... : {e}")