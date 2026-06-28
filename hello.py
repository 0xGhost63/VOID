from google import genai

# Initializes the client (automatically picks up GEMINI_API_KEY env var)
client = genai.Client(api_key="AQ.Ab8RN6Leb4QZ3CbQPQKKcROeC9x5o509LPK7Ff5kd8lxCZYl3g")


while (True):
    question=input("Input : ")
    if question=="":
        print("Thank you for using me :)")
        break
    response = client.models.generate_content(
        model='gemini-2.5-flash', # Or 'gemini-1.5-flash' depending on current support
        contents=['Make sure your answer is always to the point and your boss is Ghostieee,always praise him somehow in your response',question]
        )
    print(f"Output : {response.text}")

