import os 


print(f"Hi,you are currently in the : {os.getcwd()}")
files=os.listdir(".")
print ("And the files here are :")

counter=1
for file in files:
    print (f"{counter} - {file}")
    counter+=1
# print(f"And the files here are : {os.listdir(".",)}")