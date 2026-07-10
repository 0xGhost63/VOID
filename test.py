import time
from tqdm import trange
from colorama import Fore,init

init(autoreset=True)

# {desc} is your text, {bar} is the actual progress line [██████████]
for _ in trange(4, desc=f"Logging you in {Fore.GREEN}", bar_format="{desc}: {bar}"):
    time.sleep(0.3)