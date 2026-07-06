import sys
from supabase import create_client, ClientOptions
from dotenv import load_dotenv
import os
from simple_term_menu import TerminalMenu
from colorama import Fore,init,Back
import httpx
import time

load_dotenv()
init(autoreset=True)
SUPABASE_URL = os.getenv("PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY")

IS_LEGIT=False

def is_user_valid_huh(IS_LEGIT):
    return IS_LEGIT

try:
    
    custom_httpx_client = httpx.Client(timeout=30)

    supabase = create_client(
        SUPABASE_URL,
        SUPABASE_KEY,
        options=ClientOptions(
            httpx_client=custom_httpx_client
        )
    )
except Exception as e:
    print(f"Error : {e}")

def login ():   
    identifier=input(f"{Fore.CYAN}Enter username/email : ")
    password=input(f"{Fore.CYAN}Enter your password : ")
    email=identifier

    if "@" not in identifier:
        result = supabase.rpc("get_email_by_username", {"uname": identifier}).execute()
        if not result.data:
            print(f"{Fore.RED}No account found with that username.")
            return
        email = result.data
    try:
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        print(f"{Fore.GREEN}Login successful!")
        IS_LEGIT=False
    except Exception as e:
        print(f"{Fore.RED}{Back.BLACK}Login failed: {e}")
        print(f"{Fore.BLUE}Forgot Password ? Contact Admin.")

def register():
    print(f"{Fore.RED}INSTRUCTIONS !\n-Input a working email\n-Password length must be >= 6\n-Select a short username\nRemember your username & password")
    email=input(f"{Fore.CYAN}Enter your email : ")
    username=input(f"{Fore.CYAN}Choose a username: ")
    password = (input(f"{Fore.CYAN}Enter your password : ")).strip()
    re_enter = (input(f"{Fore.CYAN}Confirm your password : ")).strip()

    # email="0xghost63@gmail.com"
    # username="0xghost"
    # password="123456"
    # re_enter="123456"

    while(password!=re_enter):
        print(f"{Fore.RED + Back.BLACK}Error ! Password & Confirm Password doesn't match !")
        password = (input(f"{Fore.CYAN}Enter your password : ")).strip()
        re_enter = (input(f"{Fore.CYAN}Enter your password again: ")).strip()



    try:
        response = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {
                    "display_name": username
                }
            }
        })

        supabase.table("profiles").insert({
            "id": response.user.id,
            "username": username,
            "email": email
        }).execute()

        print(f"Please Wait !")

        print(f"{Fore.GREEN}Registration successful! Please check your email ({email}) to confirm your account.")
        print(f"{Fore.RED}{Back.BLACK}Plz check the spam folder in case of email is not found (or use a non-edu account)!")
        time.sleep()
        print(f"{Back.BLACK}{Fore.GREEN}Thanks for signing up..Login with your creds now :)")
        login()
    except Exception as e:
        print(f"{Fore.RED}Registration failed: {e}")




def logout():

    choice_options=["Yes","No"]
    choice_menu=TerminalMenu(choice_options,title="Are you sure to logout ? ")    
    choice_selected=choice_menu.show()
    if(choice_selected==0):
        try:
            supabase.auth.sign_out()
            print(f"{Fore.GREEN}Loging out Success ! Signing off...")
            print(f"{Fore.CYAN}Have a good day :)")
            sys.exit()

        except Exception as e:
            print(f"{Fore.RED}Logout failed: {e}")

    else:
        print(f"{Fore.CYAN}Be sure about your decisions in future :)")
        return






