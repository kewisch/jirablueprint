Jira Blueprint
==============

A tool to create Jira tickets from a YAML template file. The template can be parameterized, making it easy to create recurring Epics or sets of tickets. The code aims to be as general as possible, so it might work with more than one jira instance configured differently.

Configuration
-------------

You need a `~/.canonicalrc` like so, it should be mode 600. Using a password manager is recommended, for example using 1Password and `--config <(op inject -i ~/.canonicalrc)`

```yaml
services:
  jira:
    url: "https://warthogs.atlassian.net"
    username: "your_email"
    token: "your_jira_token"        # Get this from
  jirastage:                        #   https://id.atlassian.com/manage-profile/security/api-tokens
    url: "https://warthogs-stage.atlassian.net"
    username: "your_email"
    token: "your_jira_token"
tools:
  jirablueprint:
    templates: "template.yaml"      # Path to the templates file to use by default. This can also
    defaults:                       #  be a directory that contains multiple .yaml files.
      project: CT                   # The default project to apply if not specified in the template
    usermap:                        # A map of usernames to account ids. You need this if you want
      jira:                         #   to use the --assignee argument. To look up user ids, do a
        myalias: 1275128412841      #   JQL search for `assignee = <now autocomplete the name>`
        otheralias: 6943943852525   #   and grab it from the URL.
      jirastage:                    # If you have multiple jiras, define them per service name
        myalias: 1256986469654
```


Installation and Use
--------------------

This project uses setuptools via `pyproject.toml`. Install it as you like, one way to do so is using
`pipx install --editable .` in the source repo. It installs a `jirabp` command:

```bash
$ jirabp
Usage: jirabp [OPTIONS] COMMAND [ARGS]...

Options:
  --debug        Enable debugging
  --config TEXT  Config file location
  --jira TEXT    Which jira config to use
  --help         Show this message and exit.

Commands:
  createmeta    Show creation metadata
  dump          Dump issue fileds
  fieldmeta     Show field meta
  fields        Show field names
  fromtemplate  Create a set of issues from template
  issue         Show issue
```


Template File
-------------

Here is an example template file. No projects is specified, it is assumed this is set in the local default config.

```yaml
conference:                                                   # The name of the template
  edit: true                                                  # Force editing mode for this template (optional)
  args:                                                       # Parameters the template uses
    conference:
      description: The name of the conference, e.g. 'DebConf'
      required: true
    conference_date:
      description: The date the conference is occurring
      required: true
    url:
      description:  The URL of the conference website
  issues:                                                     # An array of top-level issues to create
    - fields:                                                 # This is the first issue
        issuetype: Epic                                       # It is an epic
        summary: "{{conference}} Conference"                    # Here we parameterize the conference name
        duedate: "{{conference_date}}"                          # Other formats such as dates are also ok
        T-shirt size: L                                       # It can also have custom fields, they
        Epic Name: "{{conference}}"                             #       start with an uppercase letter
        description: |                                        # Multiline descriptions are also fine
          Conference planning for {{conference}}.
          {% if url %}
          URL: {{url}}
          {% endif %}
      children:                                               # Here is where we define child issue
        - fields:
            issuetype: Task                                   # Just make sure the issue type is compatible
            summary: Initial Conference Brief
            T-shirt size: M
            description: |
              ....
    - fields:                                                 # We can define more top level issues
        issuetype: Epic
        summary: ...

next_template:                                                # We can also define further templates
  issues:
    - fields:
        issuetype: Task
        summary: ...
```

The template engine used is [https://jinja.palletsprojects.com](Jinja2). The following template globals are available:

* `relative_weeks(datestr: str, weeks: int) -> str`: Add/remove weeks from a certain date
  * `datestr`: The date string to add/remove weeks from
  * `weeks`: The number of weeks to add/remove
