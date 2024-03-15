from datetime import date, datetime, timedelta

import type_enforced
from jinja2 import Environment


class JiraBlueprintEnvironment(Environment):
    def __init__(self, jirabp):
        super().__init__()
        self.jirabp = jirabp

        self.globals["relative_weeks"] = self.relative_weeks
        self.globals["sprint_for_date"] = self.sprint_for_date
        self.globals["relative_sprints"] = self.relative_sprints

    def _format_sprint_date(self, datestr):
        return datetime.strptime(datestr, "%Y-%m-%dT%H:%M:%S.%fZ")

    # There are certainly smarter ways to cache/lookup the sprints, but this works (tm)
    def _find_sprint_by_date(self, target_date, board=None):
        for sprint in self.jirabp.get_sprints(board):
            if sprint.startDate and sprint.endDate:
                start_date = self._format_sprint_date(sprint.startDate)
                end_date = self._format_sprint_date(sprint.endDate)
                if start_date <= target_date <= end_date:
                    return sprint
        return None

    def _find_sprint_by_name(self, sprintstr, board=None):
        for sprint in self.jirabp.get_sprints(board):
            if sprint.name == sprintstr:
                return sprint
        return None

    @type_enforced.Enforcer
    def relative_weeks(self, datestr: str, weeks: int) -> str:
        return str(date.fromisoformat(datestr) + timedelta(weeks=weeks))

    @type_enforced.Enforcer
    def sprint_for_date(self, datestr: str, board: [int, None] = None) -> str:
        sprint = self._find_sprint_by_date(datetime.fromisoformat(datestr), board)
        if not sprint:
            raise Exception("No active/future sprint found at " + datestr)

        return sprint.name

    @type_enforced.Enforcer
    def relative_sprints(
        self, sprintstr: str, sprints: int, board: [int, None] = None
    ) -> str:
        if sprints == 0:
            return sprintstr

        sprint = self._find_sprint_by_name(sprintstr, board)
        if not sprint:
            raise Exception(f"Could not find active/future sprint {sprintstr}")

        if sprints > 0:
            end_date = self._format_sprint_date(sprint.endDate)
            new_sprint = self._find_sprint_by_date(end_date + timedelta(days=3), board)
            if not new_sprint:
                raise Exception(
                    f"Could not find active/future sprint after {sprintstr}"
                )
            return self.relative_sprints(new_sprint.name, sprints - 1, board)
        else:
            start_date = self._format_sprint_date(sprint.startDate)
            new_sprint = self._find_sprint_by_date(
                start_date - timedelta(days=3), board
            )
            if not new_sprint:
                raise Exception(
                    f"Could not find active/future sprint before {sprintstr}"
                )
            return self.relative_sprints(new_sprint.name, sprints + 1, board)
