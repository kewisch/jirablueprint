import json
import os.path
import stat

import click
import yaml

from .jirablueprint import JiraBlueprint
from .util import compile_issue_template


@click.group()
@click.option("--debug", is_flag=True, help="Enable debugging.")
@click.option("--config", default="~/.canonicalrc", help="Config file location.")
@click.option(
    "--jira",
    default="jira",
    help="Which jira config to use, refers to an entry in the services section.",
)
@click.pass_context
def main(ctx, debug, jira, config):
    ctx.ensure_object(dict)

    configpath = os.path.expanduser(config)

    # Check if the config file is locked to mode 600. Add a loophole in case it is being passed in
    # via pipe, it appears on macOS the pipes are mode 660 instead.
    statinfo = os.stat(configpath, dir_fd=None, follow_symlinks=True)
    if (statinfo.st_mode & (stat.S_IROTH | stat.S_IRGRP)) != 0 and not stat.S_ISFIFO(
        statinfo.st_mode
    ):
        raise click.ClickException(f"Credentials file {config} is not chmod 600")

    with open(configpath) as fd:
        config = yaml.safe_load(fd)

    if not config:
        raise click.ClickException(f"Could not load config file {configpath}")

    ctx.obj = JiraBlueprint(config, jira, debug)


@main.command()
@click.option("--full", is_flag=True, help="Show full field map, not just name and id.")
@click.pass_obj
def fields(ctx, full):
    """[DEBUG] Show JIRA field names.

    Show all field names in the instance with their respective field ids.
    """
    data = ctx.full_fields_map if full else ctx.fields_map
    click.echo(json.dumps(data, indent=2))


@main.command()
@click.argument("fieldname")
@click.pass_obj
def fieldmeta(ctx, fieldname):
    """[DEBUG] Show field metadata.

    Show field metadata for the field FIELDNAME (either by id or name).
    """
    all_fields = ctx.jira.fields()

    foundfield = next(
        (x for x in all_fields if x["id"] == fieldname or x["name"] == fieldname), None
    )
    click.echo(json.dumps(foundfield, indent=2))


@main.command()
@click.argument("issue")
@click.pass_obj
def issue(ctx, issue):
    """[DEBUG] Show issue fields.

    Dump the issue fields as JSON, where ISSUE is the JIRA key
    """
    click.echo(json.dumps(ctx.jira.issue(issue).raw["fields"], indent=2))


@main.command()
@click.pass_obj
@click.argument("project")
@click.argument("issuetype")
def createmeta(ctx, project, issuetype):
    """[DEBUG] Show JIRA create metadata.

    This is the information for creating an issue in PROJECT of the type ISSUETYPE (e.g. Epic).
    """
    meta = ctx.jira.createmeta(
        projectKeys=project,
        issuetypeNames=issuetype,
        expand="projects.issuetypes.fields",
    )
    click.echo(json.dumps(meta, indent=2))


@main.command()
@click.option("-f", "--file", "fname", help="Template yaml file to load from")
@click.option("-p", "--parent", help="Parent to use for the top level items")
@click.option("-n", "--dry", is_flag=True, help="Don't actually create issues")
@click.option(
    "-e", "--edit", is_flag=True, help="Revise the template before creating issues"
)
@click.argument("template_name", required=True)
@click.argument("args", nargs=-1)
@click.pass_obj
def fromtemplate(ctx, fname, template_name, args, parent, dry, edit):
    """Create a set of issues from a YAML template.

    This command will create any number of issues from your template YAML file TEMPLATE_NAME. You
    can parameterize your template using one or more ARGS, in the format key=value. If you'd like to
    apply just a subset of the issues, the --edit option will allow you to edit a copy of the
    template before it is used.

    It is recommended to set the template file path in your configuration file.
    """
    template_file = fname or ctx.toolconfig.get("template_file", None)

    if not template_file:
        raise click.UsageError(
            "You need to either pass -f or set a template_file in the tool config"
        )

    with open(os.path.expanduser(template_file)) as fd:
        templates = yaml.safe_load(fd)

    if template_name not in templates:
        raise click.BadArgumentUsage(
            f"Could not find template {template_name} in {template_file}"
        )

    template = templates[template_name]

    if edit:
        content = yaml.dump(template)
        while True:
            content = click.edit(content, extension=".yaml")
            if len(content.strip()) == 0:
                return

            try:
                template = yaml.safe_load(content)
                break
            except Exception as e:
                content = (
                    "# Exception: " + "\n# ".join(str(e).split("\n")) + "\n" + content
                )

    supplied_args = dict(kv.split("=", 1) for kv in args)

    if "args" in template:
        for arg, description in template["args"].items():
            if arg not in supplied_args:
                raise click.BadArgumentUsage(
                    f"Missing argument '{arg}' ({description})"
                )

    try:
        ctx.process_issues(template["issues"], supplied_args, parent, dry)
    except Exception as e:
        if ctx.debug:
            raise
        else:
            raise click.ClickException(f"{e}:\n\t{e.__cause__}") from e


@main.command()
@click.pass_obj
@click.argument("issuetype", required=True)
@click.option("-p", "--project", help="The project to create the issue on")
def create(ctx, issuetype, project):
    """Create a JIRA issue with your editor

    Starts an editor with some YAML that allows you to quickly create an issue. ISSUETYPE is the
    type of issue to create (e.g. Epic)
    """

    issuetype = issuetype[0].upper() + issuetype[1:]
    project = project or ctx.defaultfield("project")
    pinned = ctx.toolconfig.get("pinned", [])
    meta = ctx.jira.createmeta(
        projectKeys=project,
        issuetypeNames=issuetype,
        expand="projects.issuetypes.fields",
    )

    issuetypemeta = next(
        (x for x in meta["projects"][0]["issuetypes"] if x["name"] == issuetype), None
    )

    template = compile_issue_template(issuetypemeta, issuetype, project, pinned)

    error = "---"

    while error:
        template = click.edit(error + "\n" + template, extension=".yaml")
        if not template:
            return
        error = None

        templatedata = yaml.safe_load(template)
        issuetemplate = templatedata[issuetype.lower()]

        finaldata = {}
        for fieldid, field in issuetypemeta["fields"].items():
            if field["name"] not in issuetemplate or not issuetemplate[field["name"]]:
                continue

            finaldata[fieldid] = issuetemplate[field["name"]]

        try:
            issue = ctx.jira.create_issue(fields=finaldata)
            click.echo(issue.permalink())
        except Exception as e:
            error = "# Exception: " + "\n# ".join(str(e).split("\n")) + "\n"


if __name__ == "__main__":
    main(prog_name="jirabp")
