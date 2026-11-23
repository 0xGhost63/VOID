import pyperclip
from colorama import Fore,Back,init
import json
import random
from supabase import create_client,ClientOptions
import httpx
from datetime import datetime
from menu_compat import TerminalMenu
import authentication as athu
import dirNavigator
import os
import shutil
import sys
import socket
from configuration import configuration_check
import settings
import library

init(autoreset=True)

formatted_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def printLine():
    print(f"{Fore.LIGHTYELLOW_EX}---------------------------------------------------------------------------------------------")

def is_connected(timeout=3):
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=timeout)
        return True
    except OSError:
        return False

def menu():
  options=["~ UPLOAD FILE","~ DOWNLOAD FILE","~ SUMMARISE FILE WITH AI","~ Delete File","~ Settings","~ LOGOUT"]
  options_menu=TerminalMenu(options,title="SELECT AN OPTION TO PERFORM ")
  printLine()
  option_selected=options_menu.show()
  if option_selected is None:
      return None
  printLine()
  print(f"You selected {Fore.BLUE}{options[option_selected]}")
  return option_selected

def printQuote():
  with open("quotes.json","r") as quotes_file:
    quotes_list=json.load(quotes_file)

  random_quote=random.choice(quotes_list)
  quote=random_quote["quote"]
  author=random_quote["author"]
  printLine()
  print(f"{Back.LIGHTRED_EX}{Fore.YELLOW}{quote}")
  print(f"{Back.LIGHTRED_EX}{Fore.YELLOW}~ {author}")
  printLine()


art = f"""
{Fore.BLUE}
 ██╗   ██╗ ██████╗ ██╗██████╗ 
 ██║   ██║██╔═══██╗██║██╔══██╗
 ██║   ██║██║   ██║██║██║  ██║
 ╚██╗ ██╔╝██║   ██║██║██║  ██║
  ╚████╔╝ ╚██████╔╝██║██████╔╝
   ╚═══╝   ╚═════╝ ╚═╝╚═════╝ 
"""


printLine()
print(f"{Back.BLACK + Fore.GREEN}{art}")
print(f"{Back.BLACK}{Fore.YELLOW}   ~SORTED :)                {Fore.RED}   {formatted_time}")
printQuote()

if not is_connected():
    print(f"{Fore.RED}~ No internet connection. Please connect and restart.")
    sys.exit()

### AUTHENTICATION PROCESSSSS #####
UUID = None

options_list=["Sign In","Sign Up","Exit"]

while(not athu.is_user_valid_huh(athu.IS_LEGIT)):
    option_menu=TerminalMenu(options_list,title="Select")
    option_selected=option_menu.show()
    if (option_selected==0):
      UUID = athu.login()
    elif(option_selected==1):
      athu.register()
    elif (option_selected==2):
       printQuote()
       print(f"\n{Back.GREEN}{Fore.BLACK}Thank you :)")
       sys.exit()
       

# Prefer auth module UUID (covers Sign Up → login nested path)
UUID = athu.UUID or UUID

print(f"{Fore.LIGHTMAGENTA_EX}Checking the configs...")
configs = configuration_check(UUID)

if not configs:
  print(f"{Fore.RED}Failed to set-up the configurations...quitting :(")
  sys.exit()

lib = library.for_user(UUID)
print(f"{Fore.LIGHTMAGENTA_EX}Syncing your places...")
lib.sync(quiet=True)

import upload_file
import selectSupabaseFiles
from chat import chat_with_document



while(True):
   # #### MAIN FLOW OF THE PROGRAM ####
  action = menu()
  if action is None:
      continue

  if not is_connected():
      print(f"{Fore.RED}~ Lost internet connection. Reconnect and try again.")
      continue

  ### UPLOADING THE FILE ####
  if action == 0:
     upload_file.upload_to_supabase(UUID)
     continue

  
  ### DOWNLOADING THE FILE ! #####

  if action == 1 :
    directory=selectSupabaseFiles.selectDirectory(UUID=UUID)
    if directory is None:
        continue
    file=selectSupabaseFiles.selectFile(UUID=UUID,directory=directory)
    if file is None:
        continue

    options=["DOWNLOAD THE FILE DIRECTLY","GET A URL OF THE FILE"]
    options_menu=TerminalMenu(options,title="SELECT...")
    selected=options_menu.show()
    if selected is None:
        continue

    if selected == 0:
        try:
            source_path = lib.open_document(file["doc_id"])
            downloads = os.path.join(os.path.expanduser("~"), "Downloads")
            os.makedirs(downloads, exist_ok=True)
            destination = os.path.join(downloads, os.path.basename(source_path))
            if os.path.exists(destination):
                stem, extension = os.path.splitext(os.path.basename(source_path))
                destination = os.path.join(
                    downloads,
                    f"{stem} ({datetime.now().strftime('%Y-%m-%d %H%M%S')}){extension}",
                )
            shutil.copy2(source_path, destination)
            print(f"{Fore.GREEN}~ Saved to {destination}")
        except Exception as exc:
            print(f"{Fore.RED}~ Download failed: {exc}")

    else:
        url = lib.share_link(file["doc_id"])
        if not url:
            print(f"{Fore.YELLOW}~ This file has no cloud copy to share.")
        else:
            print(f"{Fore.GREEN}~ {url}")
            try:
                pyperclip.copy(url)
                print(f"{Fore.CYAN}~ Link copied to clipboard.")
            except Exception:
                pass
  
  ### CHATING WITH THE AI REGARDING A FILE ! 

  if action == 2:  
    directory = selectSupabaseFiles.selectDirectory(UUID=UUID)
    if directory is None:
        continue
    file = selectSupabaseFiles.selectFile(UUID=UUID, directory=directory)
    if file is None:
        continue

    chat_with_document(file["doc_id"], athu=athu)


  ## deleting a file !
  if action== 3: 
    directory=selectSupabaseFiles.selectDirectory(UUID=UUID)
    if directory is None:
        continue
    file=selectSupabaseFiles.selectFile(UUID=UUID,directory=directory)

    if file is None:
        continue

    file_name = file.get("title") or file.get("summary") or "this file"
    places = ", ".join(file.get("places", [])) or "no places"
    print(f"{Fore.RED}{Back.BLACK}Are you sure to delete : {file_name} ({places}) ?")
    yes_no_menu = TerminalMenu(["No", "Yes"], title="ARE YOU COMPLETELY SURE ?")

    if yes_no_menu.show() != 1:
      print(f"{Fore.BLUE}Backing off :)")
      continue

    errors = lib.delete_document(file["doc_id"])
    if errors:
        print(f"{Fore.YELLOW}~ Deleted, with warnings:")
        for error in errors:
            print(f"{Fore.YELLOW}  - {error}")
    else:
        print(f"{Fore.GREEN}~ '{file_name}' deleted from every connected place.")


  # $$$$$$$$$ SETTINGS $$$$$$$$
  if action == 4:
    settings.settings_menu(UUID)


  if action==5:

    athu.supabase.auth.sign_out()
    athu.ACCESS_TOKEN = ""
    athu.UUID = ""
    athu.IS_LEGIT = False
    printLine()     
    print(f"{Back.BLACK}{Fore.BLUE}~ THANK YOU :) ~")
    printLine()
    sys.exit()