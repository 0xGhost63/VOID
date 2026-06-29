from google import genai
from dotenv import load_dotenv
import os
from colorama import init,Fore,Back

init(autoreset=True)

load_dotenv()
client = genai.Client(api_key="")
inputs=[]
responses=[]

while (True):
    question=input(f"\nInput : {Fore.RED}")
    if question=="":
        print("Thank you for using me :)")
        break
    response = client.models.generate_content(
        model='gemini-2.5-flash', 
        contents=[f'Make sure your answer is always to the point(can be overriden if i said the opposite of it later in the conversation) and your boss is Ghostieee,always praise him somehow in your response & the previous context of the conversation is that the inputs i gave are {inputs} & your subsequent responses are {responses}...Moreover your response should be formmated in such a way that i can easily read and understand in the terminal ! and should be neat and clean to underastand & emojis are strictly probhited,behave in a classy gen-z way !',question,]
        )
    print(f"\nOutput : {Fore.GREEN}{Back.BLACK}{response.text}")
    inputs.append(question)
    responses.append(response.text)
    

