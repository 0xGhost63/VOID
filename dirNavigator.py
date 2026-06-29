import os 
from simple_term_menu import TerminalMenu
from colorama import Fore,init,Back

def navigate():
    FILE_SELECTED=""

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

        #SELECTING THE FILE 
        if selected_index == 3:

            ## a general list containg the files + directories
            file_cwd=os.listdir(".")  

            ## Ensuring that the user can select only a file and not the whole directory,
            ## so making a seprate smaller list only of directories from a general larger list

            files_list=["GO BACK"]
            for file in file_cwd:
                if os.path.isdir(file):
                    continue
                else :
                    files_list.append(file)

            select_menu=TerminalMenu(files_list,title="Select the file")
            slected_file=select_menu.show()
            if slected_file==0:
                continue

            FILE_SELECTED=f"{os.getcwd()}/{files_list[slected_file]}"

            print(f"{Fore.RED}You seleceted {FILE_SELECTED}")
            

    return FILE_SELECTED

