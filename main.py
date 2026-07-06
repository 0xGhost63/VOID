from colorama import Fore,Back,init
import json
import random
from tags import getTags
from datetime import datetime
from simple_term_menu import TerminalMenu
import authentication as athu

init(autoreset=True)
formatted_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def printLine():
    print(f"{Fore.LIGHTYELLOW_EX}---------------------------------------------------------------------------------------------")

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

with open("quotes.json","r") as quotes_file:
    quotes_list=json.load(quotes_file)

random_quote=random.choice(quotes_list)

quote=random_quote["quote"]
author=random_quote["author"]
printLine()
print(f"{quote}")
print(f"~{author}")
printLine()
options_list=["Sign In","Sign Up"]
option_menu=TerminalMenu(options_list,title="Select")
option_selected=option_menu.show()

if (option_selected==0):
    athu.login()
elif(option_selected==1):
    athu.register()

if(athu.is_user_valid_huh):
    print("Yo ! we are in baby !")
else:
    print ("Get your ass off ! ")
