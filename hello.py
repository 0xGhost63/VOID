from google import genai
from dotenv import load_dotenv
import os


load_dotenv()
client = genai.Client(api_key="GEMINI_API_KEY")


while (True):
    question=input("Input : ")
    if question=="":
        print("Thank you for using me :)")
        break
    response = client.models.generate_content(
        model='gemini-2.5-flash', 
        contents=['Make sure your answer is always to the point and your boss is Ghostieee,always praise him somehow in your response',question]
        )
    print(f"Output : {response.text}")

