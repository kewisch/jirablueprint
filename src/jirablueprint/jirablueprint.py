import http.client
import json
import logging
from datetime import date, timedelta
from functools import cached_property

import click
import type_enforced
from jinja2 import Environment
from jira import JIRA

from .util import ConsolePrinter


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
        self.init_jinja_environment()

        if debug:
            logging.basicConfig()
            logging.getLogger().setLevel(logging.DEBUG)
            requests_log = logging.getLogger("requests.packages.urllib3")
            requests_log.setLevel(logging.DEBUG)
            requests_log.propagate = True
            http.client.HTTPConnection.debuglevel = 1

    def init_jinja_environment(self):
        self.tenv = Environment()

        @type_enforced.Enforcer
        def relative_weeks(datestr: str, weeks: int) -> str:
            return str(date.fromisoformat(datestr) + timedelta(weeks=weeks))

        self.tenv.globals["relative_weeks"] = relative_weeks

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
        return self.tenv.from_string(value).render(**args)

    def _translate_type_value(self, key, schema, value, args):
        if key == "parent":
            return {"key": value}
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
                        key, {"type": schema["items"]}, item, args
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

            try:
                schema = self.full_fields_map[key].get("schema", {"type": "any"})
                finalfields[key] = self._translate_type_value(
                    key,
                    schema,
                    value,
                    args,
                )
            except KeyError as e:
                raise Exception(
                    f"Unknown field {e.args[0]} in '{fields.get('summary', '<unknown issue>')}'"
                ) from e
            except Exception as e:
                raise Exception(
                    f"Error evaluating '{value}' in '{fields.get('summary', '<unknown issue>')}"
                ) from e

        if "project" not in finalfields:
            finalfields["project"] = self.defaultfield("project")

        return finalfields

    def process_issues(self, issues, args, parent=None, dry=False):
        for issuemeta in issues:
            finalfields = self._translate_issue(issuemeta, args)

            if parent:
                finalfields["parent"] = {"key": parent}

            issue = None
            if dry:
                self.console.print(f"Would creating issue {finalfields['summary']}...")
                self.console.indent()
                self.console.debug(json.dumps(finalfields, indent=2))
                self.console.dedent()
            else:
                self.console.print(
                    f"Creating issue {finalfields['summary']}...", end=""
                )
                issue = self.jira.create_issue(fields=finalfields)
                self.console.print(" " + issue.permalink(), indent=False)

            if "children" in issuemeta:
                self.console.indent()
                self.process_issues(
                    issuemeta["children"], args, issue.key if issue else None, dry
                )
                self.console.dedent()
