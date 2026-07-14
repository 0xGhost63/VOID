import questionary
from questionary import Style

VOID_STYLE = Style([
    ("qmark", "fg:#00ff00 bold"),
    ("question", "fg:#00ff00 bold"),
    ("pointer", "fg:#00ff00 bold"),
    ("highlighted", "fg:#00ff00 bold"),
    ("selected", "fg:#00ff00"),
])


class TerminalMenu:
    def __init__(self, menu_entries, title=None, **kwargs):
        self.menu_entries = menu_entries
        self.title = title

    def show(self):
        choices = [
            questionary.Choice(title=str(entry), value=i)
            for i, entry in enumerate(self.menu_entries)
        ]
        try:
            return questionary.select(
                self.title or "Select an option",
                choices=choices,
                style=VOID_STYLE,
                qmark=">",
            ).ask()
        except KeyboardInterrupt:
            return None