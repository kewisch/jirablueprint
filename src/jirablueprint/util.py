import textwrap


def compile_issue_template(issuetypemeta, issuetype, project, pinned):
    template = f"{issuetype.lower()}:\n"
    for fieldid, field in sorted(
        issuetypemeta["fields"].items(), key=lambda entry: sort_pinned(pinned, entry)
    ):
        content_comment = []
        content = ""

        if field["required"] and not field["hasDefaultValue"]:
            content_comment.append("required")
        if field["schema"]["type"] == "array":
            content_comment.append("type: array of " + field["schema"]["items"])
        else:
            content_comment.append("type: " + field["schema"]["type"])

        if fieldid == "issuetype":
            content = issuetype
        elif fieldid == "project":
            content = project
        elif "allowedValues" in field:
            content = "# " + " | ".join(
                map(
                    lambda x: x.get("value", x.get("key", x.get("name", ""))),
                    field["allowedValues"],
                )
            )

        template += f"  {field['name']}: {content}"
        if content_comment:
            template += " # (" + ", ".join(content_comment) + ")"

        template += "\n"
    return template


def sort_pinned(pinned, entry):
    key, value = entry
    try:
        pinnedidx = pinned.index(value["name"])
    except ValueError:
        pinnedidx = -1

    if value["required"] and not value["hasDefaultValue"]:
        return 1
    elif value["required"]:
        return 2
    elif pinnedidx > -1:
        return 3 + pinnedidx
    else:
        return 3 + len(pinned)


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
