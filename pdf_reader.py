from dirNavigator import navigate
import pdfplumber
from colorama import Fore,Back,init
import base64
import pyperclip

init(autoreset=True)
location="/home/sannan/Documents/3rd Sem/Test.pdf"

choice=input("Would you like to view the content of the PDF/WORD file ? >> : ")
choice=choice.strip().lower()
if choice=="yes":
    counter=0
    with pdfplumber.open(location) as pdf:
        for page in pdf.pages:
            counter+=1
            print(f"The text on the page # {counter}  of the pdf file is : \n{Fore.GREEN + Back.BLACK} {page.extract_text()} ")
    counter=0
    

with open(location, "rb") as f:       
    pdf_bytes = f.read()

pdf_base64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")
print(pdf_base64)      
pyperclip.copy(pdf_base64)
print(f"{Fore.RED}Base64 PDF content is to the clipboard !")



