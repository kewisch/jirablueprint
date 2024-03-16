import http.client
import json
import logging
from collections.abc import MutableSequence
from functools import cached_property, lru_cache

import click
from jira import JIRA

from .jinjaenv import JiraBlueprintEnvironment
from .util import ConsolePrinter


class JiraBlueprint:
    def __init__(self, config, jira="jira", debug=False):
        jconfig = config["services"][jira]
        self.jiraname = jira
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
        self.tenv = JiraBlueprintEnvironment(self)

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

    @lru_cache(maxsize=None)
    def get_sprints(self, board=None):
        if not board:
            board = self.defaultfield("board")
            if not board:
                raise Exception("No default board specified in config")
        return self.jira.sprints(board, state="active,future")

    @lru_cache(maxsize=None)
    def get_sprint_dict(self, board=None):
        sprints = self.get_sprints(board)
        return {sprint.id: sprint for sprint in sprints}

    @lru_cache(maxsize=None)
    def get_sprint_name_dict(self, board=None):
        sprints = self.get_sprints(board)
        return {sprint.name: sprint for sprint in sprints}

    def _format_value(self, value, args):
        return self.tenv.from_string(value).render(**args)

    def _translate_type_value(self, key, schema, value, args):
        if key == "parent":
            return {"key": value}

        if schema.get("custom", "") == "com.pyxis.greenhopper.jira:gh-sprint":
            # Slight adjustment so we can deal with this as a standard array
            schema["items"] = "com.pyxis.greenhopper.jira:gh-sprint"

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
            if not isinstance(value, MutableSequence):
                raise Exception(
                    f"Value for {self.fields_map.get(key, key)} must be a list, not a scalar: {value}"
                )

            return list(
                map(
                    lambda item: self._translate_type_value(
                        key, {"type": schema["items"]}, item, args
                    ),
                    value,
                )
            )
        elif schema["type"] == "com.pyxis.greenhopper.jira:gh-sprint":
            if isinstance(value, dict):
                board = value["board"]
                formatted = self._format_value(value["sprint"], args)
            else:
                board = None
                formatted = self._format_value(value, args)

            if isinstance(formatted, int):
                return {"board": board, "sprint": formatted}
            elif isinstance(formatted, str):
                sprints = self.get_sprints(board)
                for sprint in sprints:
                    if sprint.name == formatted:
                        return {"board": board, "id": sprint.id}
                raise Exception(f"Could not find active/future sprint: {formatted}")
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

    def process_issues(self, issues, args, parent=None, assignee=None, dry=False):
        for issuemeta in issues:
            finalfields = self._translate_issue(issuemeta, args)

            if parent:
                finalfields["parent"] = {"key": parent}

            if assignee:
                finalfields["assignee"] = {"id": assignee}

            addsprints = []
            sprintfield = self.rev_fields_map.get("Sprint", None)
            if sprintfield and sprintfield in finalfields:
                # We need to add the sprint using a different api
                addsprints = finalfields[sprintfield]
                del finalfields[sprintfield]

                def map_sprint(item):
                    sprintdict = self.get_sprint_dict(item["board"])[item["id"]].name
                    return sprintdict[item["id"]].name

                sprintinfo = ",".join(map(map_sprint, addsprints))

            issue = None
            if dry:
                if len(addsprints):
                    self.console.print(
                        f"Would creating issue {finalfields['summary']} in {sprintinfo}"
                    )
                else:
                    self.console.print(f"Would creating issue {finalfields['summary']}")
                self.console.indent()
                self.console.debug(json.dumps(finalfields, indent=2))
                self.console.dedent()
            else:
                if len(addsprints):
                    self.console.print(
                        f"Creating issue {finalfields['summary']} in {sprintinfo}...",
                        end="",
                    )
                else:
                    self.console.print(
                        f"Creating issue {finalfields['summary']}...", end=""
                    )
                issue = self.jira.create_issue(fields=finalfields)
                self.console.print(" " + issue.permalink(), indent=False)

                for sprint in addsprints:
                    self.jira.add_issues_to_sprint(sprint["id"], [issue.key])

            if "children" in issuemeta:
                self.console.indent()
                self.process_issues(
                    issuemeta["children"], args, issue.key if issue else None, dry
                )
                self.console.dedent()
