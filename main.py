from colorama import Fore,Back,init
import json
import random
from tags import getTags
from datetime import datetime

init(autoreset=True)
formatted_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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


print(f"{Back.BLACK + Fore.GREEN}{art}")

with open("quotes.json","r") as quotes_file:
    quotes_list=json.load(quotes_file)

random_quote=random.choice(quotes_list)

quote=random_quote["quote"]
author=random_quote["author"]
print(f"{quote}")
print(f"~{author}")

tags=getTags()
print (f"The tags extracted are : {tags}")

