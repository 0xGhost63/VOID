import os 
from colorama import Fore,Back,init


init(autoreset=True)

everything_ok = False

def change_subjects():
    print(f"{Fore.RED}{Back.BLACK}ENTER THE SUBJECTS YOU ARE CURRENTLY ENROLLED IN (ONE-TIME SETUP),enter 'exit' or 'quit' to end : ")
    counter = 1
    subjects=[]
    quit_options=["EXIT","QUIT","Q","E"]
    while(True):
        temp=input(f"{Fore.LIGHTBLUE_EX}Enter the subject # {counter} : ").strip().upper()
        if temp in quit_options : 
            break
        else:
            subjects.append(temp)
            counter+=1
    try :
        with open ("subjects.py","w") as file:
            file.write(f""" 
def getSub():
    subjects = {subjects}
    return subjects""")

        global everything_ok
        everything_ok = True
        print(f"{Fore.GREEN}DONE WITH THE CONFIGURATIONS !")
        return everything_ok



    except Exception as e:
        print(f"{Fore.RED}Error :( : {e}")
        return False


    
def configuration_check():
    cwd=os.listdir()
    if "subjects.py" in cwd:
        print(f"{Fore.GREEN}Good to go !")
        global everything_ok
        everything_ok = True
        return everything_ok
    else:
        return change_subjects()

