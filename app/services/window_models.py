"""Target identities shared by Windows and Android device pickers."""
from dataclasses import dataclass
from app.utils.window_settings_store import WindowSelection

@dataclass
class WindowCandidate:
    '''A visible top-level window plus its resolved Google Play Games game surface (if any).'''
    # [recovered from bytecode: decompiler collapsed these fields into the docstring]
    top_hwnd: int | str = 0
    title: str = ''
    top_class: str = ''
    child_hwnd: int | str = 0
    child_class: str = ''

    @property
    def is_game(self):
        '''True when this window exposes a CROSVM game surface we can capture.'''
        return self.child_hwnd != 0


    def to_selection(self):
        return WindowSelection(title = self.title, top_class = self.top_class, child_class = self.child_class)


    def display_label(self):
        title = self.title or '(no title)'
        if self.is_game:
            return f'''{title}  —  surface: {self.child_class}'''
        return f'''{title}  —  no game surface ({self.top_class})'''



@dataclass
class DescendantInfo:
    '''A single descendant window under a top-level window (for the Info diagnostics view).'''
    # [recovered from bytecode: decompiler collapsed these fields into the docstring]
    hwnd: int | str
    cls: str
    title: str
    width: int
    height: int
    depth: int
    is_surface: bool

    def display_label(self):
        indent = '    ' * self.depth
        marker = '[surface] ' if self.is_surface else ''
        size = f'''{self.width}x{self.height}''' if self.width and self.height else '—'
        title = f'''  "{self.title}"''' if self.title else ''
        return f'''{indent}{marker}{self.cls}  ({size})  hwnd={self.hwnd}{title}'''
