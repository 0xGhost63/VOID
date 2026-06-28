import os 
from simple_term_menu import TerminalMenu
from colorama import Fore,init,Back


init(autoreset=True)
commands=[
    "~ LIST FILES IN DIR",
    "~ CHANGE DIRECTORY",
    "~ MOVE BACK",
    "~ Select ",
    "~ EXIT",]


menu=TerminalMenu(commands,title=f"Select a command to perform")
while(True):
    selected_index=menu.show()

    print(f"You selected {commands[selected_index]}")

    #EXITING 
    if (selected_index==4):
        break

    #LISTING THE FILES IN THE DIRECTORY ! 
    if selected_index==0:
        print(f"{Fore.BLUE}ls {os.getcwd()}")  
        files=os.listdir(".")
        for file in files:
            if os.path.isdir(file):
                print(f"{Back.YELLOW + Fore.BLACK} ~ {file} [DIR] ")
            else:
                print(f"{Back.YELLOW + Fore.BLACK} ~ {file} [FILE] ")

    #Changing the directory 
    if selected_index==1:
        print(f"{Fore.GREEN}You are currently at : {os.getcwd()}")
        print("Enter the directory to navigate to !")

        while(True):
            dir=input(f"{Fore.BLUE}@User : cd ")
            if(os.path.exists(dir)):
                os.chdir(dir)
                print(f"{Fore.GREEN}You are now at : {os.getcwd()}")
                break
            else :
                print(f"{Fore.RED}Invalid path :(...{dir} doesn't exist !")

    #MOVING BACK
    if selected_index==2:
        print (f"{Fore.RED}Previous working dir : {os.getcwd()}")
        os.chdir('..')
        print(f"{Fore.GREEN}You are now at : {os.getcwd()}")
        

            



