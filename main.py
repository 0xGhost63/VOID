import pyperclip
from colorama import Fore,Back,init
import json
import random
from supabase import create_client,ClientOptions
import httpx
from datetime import datetime
from simple_term_menu import TerminalMenu
import authentication as athu
import dirNavigator
import os
import sys
import socket
from configuration import configuration_check
import settings

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
       

print(f"{Fore.LIGHTMAGENTA_EX}Checking the configs...")
configs=configuration_check()

if not configs :
  print(f"{Fore.RED}Failed to set-up the configurations...quitting :(")
  sys.exit()

from subjects import getSub 
from pdf_sumariser import summarise
import upload_file
import selectSupabaseFiles
from chat import chat_with_file



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

    storage_path=file["storage_path"]

    options=["DOWNLOAD THE FILE DIRECTLY","GET A URL OF THE FILE"]
    options_menu=TerminalMenu(options,title="SELECT...")
    selected=options_menu.show()
    if selected is None:
        continue
  
  ### CHATING WITH THE AI REGARDING A FILE ! 

  if action == 2:  
    directory = selectSupabaseFiles.selectDirectory(UUID=UUID)
    if directory is None:
        continue
    file = selectSupabaseFiles.selectFile(UUID=UUID, directory=directory)
    if file is None:
        continue

    chat_with_file(file["storage_path"],athu=athu)


  ## deleting a file !
  if action== 3: 
    directory=selectSupabaseFiles.selectDirectory(UUID=UUID)
    if directory is None:
        continue
    file=selectSupabaseFiles.selectFile(UUID=UUID,directory=directory)

    if file is None:
        continue
    
    storage_path=file["storage_path"]
    file_name=storage_path.split("/")
    file_name=file_name[2]

    print(f"{Fore.RED}{Back.BLACK}Are you sure to delete the : {file_name}")
    yes_no_menu = TerminalMenu(["No", "Yes"], title="ARE YOU COMPLETELY SURE ?")

    if yes_no_menu.show() == 0:
      print(f"{Fore.BLUE}Backing off :)")
      continue

    if yes_no_menu.show() == 1:
       
      table_deleted = False

      try:
          athu.supabase.table("USERS_DATA").delete().eq("storage_path", storage_path).eq("USER_ID", UUID).execute()
          table_deleted = True

          athu.supabase.storage.from_("VOID_FILES").remove([storage_path])
          print(f"{Fore.GREEN}~ '{file_name}' deleted from both database and storage.")
      except httpx.ConnectError:
          print(f"{Fore.RED}~ Connection lost mid-delete. Check your internet and try again :(")
      except Exception as e:
          print(f"{Fore.RED}~ Delete failed: {e}")

          if table_deleted:
              print(f"{Fore.YELLOW}~ Warning: DB record removed but file may still exist in storage. Manual cleanup may be needed.")


  # $$$$$$$$$ SETTINGS $$$$$$$$
  if action == 4 :
    settings.settings_menu()


  if action==5:

    athu.supabase.auth.sign_out()
    printLine()     
    print(f"{Back.BLACK}{Fore.BLUE}~ THANK YOU :) ~")
    printLine()
    sys.exit()