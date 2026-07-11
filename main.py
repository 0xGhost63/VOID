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
from pdf_sumariser import summarise
from subjects import getSub 

init(autoreset=True)

formatted_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def printLine():
    print(f"{Fore.LIGHTYELLOW_EX}---------------------------------------------------------------------------------------------")

def menu():
  options=["~ UPLOAD FILE","~ DOWNLOAD FILE","~ SUMMARISE FILE WITH AI","~ Delete File","~ Settings","~ LOGOUT"]
  options_menu=TerminalMenu(options,title="SELECT AN OPTION TO PERFORM ")
  printLine()
  option_selected=options_menu.show()
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


art =f"""

         ███             ███             ███ 
       ███░            ███░            ███░  
     ███░            ███░            ███░    
   ███░            ███░            ███░      
 ███░            ███░            ███░        
██░            ███░            ███░          
░            ███░            ███░            
            ░░░             ░░░             ░
     ██__   __  _______█ ___  ______███     
   ███|  | |  ||       ||   ||      |░      
 ███░ |  |_|  ||   _   ||   ||  _    |      
██░   |       ||  | |  ||   || | |   |                  {Fore.RED}{formatted_time}
░     |       ||  |_|  ||   || |_|   |      
       |     |░|       ||   ||       |    ██
        |___|  |_______||___||______|   ███░
        ░░░             ░░░             ░░░  
 ███             ███             ███        
██░            ███░            ███░          
░            ███░            ███░            
           ███░            ███░            ██
         ███░            ███░            ███░
       ███░            ███░            ███░  
     ███░            ███░            ███░"""


printLine()
print(f"{Back.BLACK + Fore.GREEN}{art}")
printLine()

printQuote()

### AUTHENTICATION PROCESSSSS #####
UUID = None

# options_list=["Sign In","Sign Up","Exit"]

# while(not athu.is_user_valid_huh(athu.IS_LEGIT)):
#     option_menu=TerminalMenu(options_list,title="Select")
#     option_selected=option_menu.show()
#     if (option_selected==0):
#       UUID = athu.login()
#     elif(option_selected==1):
#       athu.register()
#     elif (option_selected==2):
#        printQuote()
#        print(f"\n{Back.GREEN}{Fore.BLACK}Thank you :)")
#        sys.exit()
       
  
UUID=athu.login()
files = athu.supabase.storage.from_("VOID_FILES").list(f"{UUID}/DSA")
print (files)
       

# #### MAIN FLOW OF THE PROGRAM ####
# action = menu()

# ### UPLOADING THE FILE ####
# if action == 0:
#   file_selected = dirNavigator.navigate()
#   result=summarise(file_location=file_selected)
#   tags=result.split(':')
#   print(f"The tags for this documents are : ")
#   print(f"{Fore.CYAN}SUBJECT  : {tags[0]}")
#   print(f"{Fore.CYAN}CATEGORY : {tags[1]}")
#   print(f"{Fore.CYAN}SUMMARY  : {tags[2]}")
#   yes_no_options=["No","Yes"]
#   yes_no_menu=TerminalMenu(yes_no_options,title="WOULD YOU LIKE TO EDIT ANY TAG ?(incase of handwritten notes)")
#   yes_no_selected=yes_no_menu.show()

#   if yes_no_selected == 1:
#     tags_menu = TerminalMenu(tags,title="Select the tag to change")
#     tags_selected=tags_menu.show()

#     if tags_selected == 0 :
#       allowed_subjects=getSub()
#       subject=input(f"{Fore.BLUE}Enter the Subject,choose from {Fore.RED} {allowed_subjects} : ").strip()
#       while(True):
#         if subject in allowed_subjects:
#           break
#         else:
#           subject=input(f"{Fore.RED}Choose again,only from ({allowed_subjects})").strip()

#       tags[0]=subject

#     elif tags_selected==1 :
#       category = input(f"{Fore.BLUE}Enter the Category : ")
#       tags[1]=category

#     elif tags_selected==2 :
#       summary=input(f"{Fore.BLUE}Enter the Summary : ")
#       tags[2]=summary
  

#   with open(file_selected,"rb") as file :
#     try :
#       filename=os.path.basename(file_selected)
#       tags[0]=tags[0].strip()
#       supa_storage_path=f"{UUID}/{tags[0]}/{filename}"

#       response = athu.supabase.storage.from_("VOID_FILES").upload(
#           path=supa_storage_path,
#           file=file
#       )

#       # print(response)
#       print(f"{Fore.GREEN}{Back.YELLOW}~ {filename} uploaded successfully at path {supa_storage_path}") 
    
#     except Exception as e:
#       print(f"{Fore.RED}{Back.BLACK}Error Pushing the file ({filename} bcuz of : {e})")
       
# # if action == 1 :
