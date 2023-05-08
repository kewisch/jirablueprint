import textwrap


class ConsolePrinter:
    def __init__(self, debug):
        self._debug = debug
        self._indent = 0

    def indent(self):
        self._indent += 1

    def dedent(self):
        self._indent -= 1

    def printlines(self, text):
        print(textwrap.indent(text, "\t" * self._indent))

    def print(self, *args, end="\n", indent=True):
        if indent:
            data = " ".join(args)
            print(textwrap.indent(data, "\t" * self._indent), end=end)
        else:
            print(*args, end=end)

    def debug(self, *args, end="\n", indent=True):
        if self._debug:
            self.print(*args, end=end)
