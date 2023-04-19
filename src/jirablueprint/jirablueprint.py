import http.client
import logging
from functools import cached_property

import click
from jira import JIRA


class ConsolePrinter:
    def __init__(self, debug):
        self._debug = debug
        self._indent = 0

    def indent(self):
        self._indent += 1

    def dedent(self):
        self._indent -= 1

    def print(self, *args, end="\n", indent=True):
        if indent:
            print("\t" * self._indent + str(args[0]), *args[1:], end=end)
        else:
            print(*args, end=end)

    def debug(self, *args, end="\n", indent=True):
        if self._debug:
            self.print(*args, end=end)


class JiraBlueprint:
    def __init__(self, config, jira="jira", debug=False):
        jconfig = config["services"][jira]
        self.jira = JIRA(
            jconfig["url"],
            basic_auth=(jconfig["username"], jconfig["token"]),
        )

        self.toolconfig = (
            config["tools"]["jirablueprint"]
            if "jirablueprint" in config["tools"]
            else {}
        )
        self.serviceconfig = config["services"]
        self.debug = debug
        self.console = ConsolePrinter(debug)

        if debug:
            logging.basicConfig()
            logging.getLogger().setLevel(logging.DEBUG)
            requests_log = logging.getLogger("requests.packages.urllib3")
            requests_log.setLevel(logging.DEBUG)
            requests_log.propagate = True
            http.client.HTTPConnection.debuglevel = 1

    @cached_property
    def full_fields_map(self):
        all_fields = self.jira.fields()
        return {field["id"]: field for field in all_fields}

    @cached_property
    def fields_map(self):
        all_fields = self.jira.fields()
        return {field["id"]: field["name"] for field in all_fields}

    @cached_property
    def rev_fields_map(self):
        all_fields = self.jira.fields()
        return {field["name"]: field["id"] for field in all_fields}

    def defaultfield(self, name, default=None):
        if "defaults" not in self.toolconfig:
            return default

        return self.toolconfig["defaults"].get(name, default)

    def _format_value(self, value, args):
        try:
            return str(value).format(**args)
        except KeyError as e:
            raise click.UsageError(f"Missing arg '{e.args[0]}' in field: {value}")

    def _translate_type_value(self, schema, value, args):
        if schema["type"] in ("string", "date", "datetime", "option2", "any"):
            return self._format_value(value, args)
        elif schema["type"] == "number":
            return int(value)
        elif schema["type"] in ("issuetype", "status", "priority", "component"):
            return {"name": self._format_value(value, args)}
        elif schema["type"] == "user":
            return {"accountId": self._format_value(value, args)}
        elif schema["type"] == "option":
            return {"value": self._format_value(value, args)}
        elif schema["type"] == "array":
            return list(
                map(
                    lambda item: self._translate_type_value(
                        {"type": schema["items"]}, item, args
                    ),
                    value,
                )
            )
        else:
            raise Exception("Unknown field type: " + str(schema))

    def _translate_issue(self, issuemeta, args):
        fields = issuemeta["fields"]
        finalfields = {}

        for key, value in fields.items():
            # field ids start lowercase, everything else is a custom field name
            if not key[0].islower():
                if key not in self.rev_fields_map:
                    raise click.UsageError(f"'{key}' is not a valid field id or name")
                key = self.rev_fields_map[key]

            finalfields[key] = self._translate_type_value(
                self.full_fields_map[key]["schema"], value, args
            )

        if "project" not in finalfields:
            finalfields["project"] = self.defaultfield("project")

        return finalfields

    def process_issues(self, issues, args, parent=None):
        for issuemeta in issues:
            finalfields = self._translate_issue(issuemeta, args)

            if parent:
                finalfields["parent"] = {"key": parent}

            self.console.print(f"Creating issue {finalfields['summary']}...", end="")
            self.console.debug(finalfields, end="")
            issue = self.jira.create_issue(fields=finalfields)
            self.console.print(" " + issue.permalink(), indent=False)

            if "children" in issuemeta:
                self.console.indent()
                self.process_issues(issuemeta["children"], args, issue.key)
                self.console.dedent()
