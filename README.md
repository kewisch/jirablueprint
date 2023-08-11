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
$ jirabp --help
Usage: jirabp [OPTIONS] COMMAND [ARGS]...

Options:
  --debug        Enable debugging.
  --config TEXT  Config file location.
  --jira TEXT    Which jira config to use, refers to an entry in the services
                 section.
  --help         Show this message and exit.

Commands:
  create        Create a JIRA issue with your editor.
  createmeta    [DEBUG] Show JIRA create metadata.
  fieldmeta     [DEBUG] Show field metadata.
  fields        [DEBUG] Show JIRA field names.
  fromtemplate  Create a set of issues from a YAML template.
  issue         [DEBUG] Show issue fields.
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


Tips & Tricks
-------------

### Default Arguments

You can make use of jinja's default() filter to do default arguments:
```yaml
defaultargs:
  args:
    summary:
      description: Ticket summary
  issues:
    - fields:
        issuetype: Task
        summary: "{{summary|default('default summary')}}"
```

### Calculate fields

Jinja has [a bunch of neat built-ins](https://jinja.palletsprojects.com/en/3.1.x/templates).
Calculate fields based on args:

```yaml
merchandise:
  args:
    attendees:
      description: How may people are coming
  issues:
    - fields:
      issuetype: Task
      summary: Order merch
      description: |
        Order merch for conference. {{attendees}} attendees.
          * {{ (1.5 * attendees)|round }} stickers round
          * {{ (0.8 * attendees)|round }} stickers square

```

### Set parent issue

You can attach a bunch of tasks to an epic using the `--parent` argument:

```yaml
attachtoepic:
  issues:
    - fields:
        issuetype: Task
        summary: Task 1
    - fields:
        issuetype: Task
        summary: Task 2
```

`jirabp fromtemplate attachtoepic -p EPICS-123`

### Don't repeat yourself with YAML

You can make use of YAML anchors and aliases to not repeat yourself, e.g. include one set of issues in the next:

```yaml
smaller_task:
  issues: &smaller_task_issues
    - fields:
        issuetype: Task
        summary: Task 1
    - fields:
        issuetype: Task
        summary: Task 2

bigger_picture:
  issues:
    - fields:
        issuetype: Epic
        summary: Epic 1
      children: *smaller_task_issues

```

The tool doesn't do strict semantic parsing on the yaml, so you can also drop some anchors into an unused section and reuse them:

```yaml
chicken:
  mydefaults:
    - &chicken chicken
  issues:
    - fields:
        issuetype: Epic
        summary: *chicken
      children:
        - fields:
           issuetype: Task
           summary: *chicken
        - fields:
           issuetype: Task
           summary: *chicken
```
