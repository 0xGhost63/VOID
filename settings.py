######## TO BE COMPLETED LATER
# -PASSWORDS
# -CLOUD MANAGEMENT etc...

from configuration import change_subjects
from simple_term_menu import TerminalMenu
from colorama import Fore,Back,init
init(autoreset=True)


### change the subjects
def change_user_subjects () :
    yes_no=["YES","NO"]
    yes_no_menu=TerminalMenu(yes_no,title="Are you sure to change the subjects ? ")
    yes_no_selected=yes_no_menu.show()

    if yes_no_selected ==  1:
        print(f"{Fore.LIGHTMAGENTA_EX}Retreating.... :)")
        return
    else :
        change_subjects()
        print(f"{Fore.GREEN}Done changing the subjects")
        from subjects import getSub
        subjects=getSub()
        print(f"{Fore.BLUE}Your new subjects are : ")
        for subject in subjects :
            print(f"{Fore.CYAN}~ {subject}")


# $$$$$$$ settings options $$$$$$$ #

def settings_menu():
    while(True):
        settings_list=["CHANGE SUBJECTS"]
        settings_list.insert(0,"EXIT SETTINGS")
        settings_Menu=TerminalMenu(settings_list,title="CHOOSE THE SETTINGS OPTION")
        settings_selected=settings_Menu.show()

        if settings_selected == None :
            continue
        elif settings_selected == 0 :
            print(f"{Fore.CYAN}Retreating... :)")
            break

        elif settings_selected == 1 :
            change_user_subjects()