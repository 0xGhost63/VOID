from google import genai
from dotenv import load_dotenv
import os
from colorama import init,Fore,Back

init(autoreset=True)

load_dotenv()
client = genai.Client(api_key="")
location="/home/sannan/Documents/3rd Sem/Test.pdf"
file = client.files.upload(file=location)

response = client.models.generate_content(
model='gemini-2.5-flash', 
contents=[f'Summarise this file !',file])
print(f"\nOutput : {Fore.GREEN}{Back.BLACK}{response.text}")


