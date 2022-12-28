from json import JSONDecodeError
from typing import IO, Optional, Sequence

from pydantic import parse_obj_as
from requests import HTTPError, Session

from .entities import BaseModel, Issue, IssueAttachment, IssueComment, IssueCustomFieldType, IssueTag, Project, User
from .exceptions import YouTrackException, YouTrackNotFound, YouTrackUnauthorized
from .helpers import model_to_field_names, obj_to_json


class Client:
    def __init__(self, *, base_url: str, token: str):
        self._base_url = base_url
        self._session = Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
            },
        )

    def _build_url(
        self,
        *,
        path: str,
        fields: Optional[str] = None,
        offset: Optional[int] = None,
        count: Optional[int] = None,
    ) -> str:
        query = "&".join(
            tuple(
                f"{key}={value}"
                for key, value in {
                    "fields": fields,
                    "$skip": offset,
                    "$top": count,
                }.items()
                if value is not None
            ),
        )

        return f"{self._base_url}/api{path}?{query}"

    def _send_request(
        self,
        *,
        method: str,
        path: str,
        params: Optional[dict] = None,
        data: Optional[BaseModel] = None,
        files: Optional[dict[str, IO]] = None,
    ) -> Optional[dict]:
        response = self._session.request(
            method=method,
            url=f"{self._base_url}/api{path}",
            params=params,
            # url=self._build_url(path=path, fields=fields, offset=offset, count=count),
            data=data and obj_to_json(data),
            files=files,
            headers=data and {"Content-Type": "application/json"},
        )

        if response.status_code == 404:
            raise YouTrackNotFound
        elif response.status_code == 401:
            raise YouTrackUnauthorized
        else:
            try:
                response.raise_for_status()
            except HTTPError as e:
                raise YouTrackException(
                    f"Unexpected status code for {method} {path}: {response.status_code}.",
                ) from e

        # Avoid JSONDecodeError if status code was 2xx, but the response content is empty.
        # Some API endpoints return empty, non-JSON responses on success.
        if len(response.content) == 0:
            return

        try:
            return response.json()
        except JSONDecodeError as e:
            raise YouTrackException(
                f"Failed to decode response from {method} {path}, status={response.status_code}",
            ) from e

    def _get(
        self,
        *,
        path: str,
        fields: Optional[str] = None,
        query: Optional[str] = None,
        offset: Optional[int] = None,
        count: Optional[int] = None,
    ) -> Optional[dict]:
        return self._send_request(
            method="GET",
            path=path,
            params={
                key: value
                for key, value in {
                    "fields": fields,
                    "query": query,
                    "$skip": offset,
                    "$top": count,
                }.items()
                if value is not None
            },
        )

    def _post(
        self,
        *,
        path: str,
        fields: Optional[str] = None,
        offset: Optional[int] = None,
        count: Optional[int] = None,
        data: Optional[BaseModel] = None,
        files: Optional[dict[str, IO]] = None,
    ) -> Optional[dict]:
        return self._send_request(
            method="POST",
            path=path,
            params={
                key: value
                for key, value in {
                    "fields": fields,
                    "$skip": offset,
                    "$top": count,
                }.items()
                if value is not None
            },
            data=data,
            files=files,
        )

    def _delete(self, *, path: str) -> Optional[dict]:
        return self._send_request(method="DELETE", path=path)

    def get_issues(self, *, query: str, offset: int = 0, count: int = -1, raw: bool = False) -> Sequence[Issue]|dict:
        """Query for issues

        https://www.jetbrains.com/help/youtrack/devportal/operations-api-issues.html#get-Issue-method
        """
        result = self._get(
            path="/issues",
            query=query,
            fields=model_to_field_names(Issue),
        )
        if raw:
            return result
        return parse_obj_as(
            tuple[Issue, ...],
            result,
        )

    def get_issue(self, *, issue_id: str, raw: bool = False) -> Issue:
        """Read an issue with specific ID.

        https://www.jetbrains.com/help/youtrack/devportal/operations-api-issues.html#get-Issue-method
        """
        result = self._get(
            path=f"/issues/{issue_id}",
            fields=model_to_field_names(Issue),
        )
        if raw:
            return result
        return Issue.parse_obj(result)

    def create_issue(self, *, issue: Issue) -> Issue:
        """Create new issue.

        https://www.jetbrains.com/help/youtrack/devportal/resource-api-issues.html#create-Issue-method
        """
        return Issue.parse_obj(
            self._post(
                path="/issues",
                fields=model_to_field_names(Issue),
                data=issue,
            ),
        )

    def get_issue_custom_fields(
        self,
        *,
        issue_id: str,
        offset: int = 0,
        count: int = -1,
    ) -> Sequence[IssueCustomFieldType]:
        """Get the list of available custom fields of the issue.

        https://www.jetbrains.com/help/youtrack/devportal/resource-api-issues-issueID-customFields.html#get_all-IssueCustomField-method
        """
        return parse_obj_as(
            tuple[IssueCustomFieldType, ...],
            self._get(
                path=f"/issues/{issue_id}/customFields",
                fields=model_to_field_names(IssueCustomFieldType),
                offset=offset,
                count=count,
            ),
        )

    def update_issue_custom_field(self, *, issue_id: str, field: IssueCustomFieldType) -> IssueCustomFieldType:
        """Update specific custom field in the issue.

        https://www.jetbrains.com/help/youtrack/devportal/operations-api-issues-issueID-customFields.html#update-IssueCustomField-method
        """
        return parse_obj_as(
            IssueCustomFieldType,
            self._post(
                path=f"/issues/{issue_id}/customFields/{field.id}",
                fields=model_to_field_names(IssueCustomFieldType),
                data=field,
            ),
        )

    def delete_issue(self, *, issue_id: str):
        """Delete the issue.

        https://www.jetbrains.com/help/youtrack/devportal/operations-api-issues.html#delete-Issue-method
        """
        self._delete(path=f"/issues/{issue_id}")

    def get_issue_comments(self, *, issue_id: str, offset: int = 0, count: int = -1) -> Sequence[IssueComment]:
        """Get all accessible comments of the specific issue.

        https://www.jetbrains.com/help/youtrack/devportal/resource-api-issues-issueID-comments.html#get_all-IssueComment-method
        """
        return parse_obj_as(
            tuple[IssueComment, ...],
            self._get(
                path=f"/issues/{issue_id}/comments",
                fields=model_to_field_names(IssueComment),
                offset=offset,
                count=count,
            ),
        )

    def create_issue_comment(self, *, issue_id: str, comment: IssueComment) -> IssueComment:
        """Add a new comment to an issue with a specific ID.

        https://www.jetbrains.com/help/youtrack/devportal/resource-api-issues-issueID-comments.html#create-IssueComment-method
        """
        return IssueComment.parse_obj(
            self._post(
                path=f"/issues/{issue_id}/comments",
                fields=model_to_field_names(IssueComment),
                data=comment,
            ),
        )

    def update_issue_comment(self, *, issue_id: str, comment: IssueComment) -> IssueComment:
        """Update an existing comment of the specific issue.

        https://www.jetbrains.com/help/youtrack/devportal/operations-api-issues-issueID-comments.html#update-IssueComment-method
        """
        return IssueComment.parse_obj(
            self._post(
                path=f"/issues/{issue_id}/comments/{comment.id}",
                fields=model_to_field_names(IssueComment),
                data=comment,
            ),
        )

    def hide_issue_comment(self, *, issue_id: str, comment_id: str):
        """Hide a specific issue comment.

        https://www.jetbrains.com/help/youtrack/devportal/operations-api-issues-issueID-comments.html#update-IssueComment-method
        """
        self.update_issue_comment(issue_id=issue_id, comment=(IssueComment(id=comment_id, deleted=True)))

    def delete_issue_comment(self, *, issue_id: str, comment_id: str):
        """Delete a specific issue comment.

        https://www.jetbrains.com/help/youtrack/devportal/operations-api-issues-issueID-comments.html#delete-IssueComment-method
        """
        self._delete(path=f"/issues/{issue_id}/comments/{comment_id}")

    def get_issue_attachments(self, *, issue_id: str, offset: int = 0, count: int = -1) -> Sequence[IssueAttachment]:
        """Get a list of all attachments of the specific issue.

        https://www.jetbrains.com/help/youtrack/devportal/resource-api-issues-issueID-attachments.html#get_all-IssueAttachment-method
        """
        return parse_obj_as(
            tuple[IssueAttachment, ...],
            self._get(
                path=f"/issues/{issue_id}/attachments",
                fields=model_to_field_names(IssueAttachment),
                offset=offset,
                count=count,
            ),
        )

    def create_issue_attachments(self, *, issue_id: str, files: dict[str, IO]) -> Sequence[IssueAttachment]:
        """Add an attachment to the issue.

        https://www.jetbrains.com/help/youtrack/devportal/resource-api-issues-issueID-attachments.html#create-IssueAttachment-method
        https://www.jetbrains.com/help/youtrack/devportal/api-usecase-attach-files.html
        """
        return parse_obj_as(
            tuple[IssueAttachment, ...],
            self._post(
                path=f"/issues/{issue_id}/attachments",
                fields=model_to_field_names(IssueAttachment),
                files=files,
            ),
        )

    def create_comment_attachments(
        self,
        *,
        issue_id: str,
        comment_id: str,
        files: dict[str, IO],
    ) -> Sequence[IssueAttachment]:
        return parse_obj_as(
            tuple[IssueAttachment, ...],
            self._post(
                path=f"/issues/{issue_id}/comments/{comment_id}/attachments",
                fields=model_to_field_names(IssueAttachment),
                files=files,
            ),
        )

    def get_projects(self, offset: int = 0, count: int = -1) -> Sequence[Project]:
        """Get a list of all available projects in the system.

        https://www.jetbrains.com/help/youtrack/devportal/resource-api-admin-projects.html#get_all-Project-method
        """
        return parse_obj_as(
            tuple[Project, ...],
            self._get(
                path="/admin/projects",
                fields=model_to_field_names(Project),
                offset=offset,
                count=count,
            ),
        )

    def get_tags(self, offset: int = 0, count: int = -1) -> Sequence[IssueTag]:
        """Get all tags that are visible to the current user.

        https://www.jetbrains.com/help/youtrack/devportal/resource-api-issueTags.html#get_all-IssueTag-method
        """
        return parse_obj_as(
            tuple[IssueTag, ...],
            self._get(
                path="/issueTags",
                fields=model_to_field_names(IssueTag),
                offset=offset,
                count=count,
            ),
        )

    def add_issue_tag(self, *, issue_id: str, tag: IssueTag):
        self._post(
            path=f"/issues/{issue_id}/tags",
            data=tag,
        )

    def get_users(self, offset: int = 0, count: int = -1) -> Sequence[User]:
        """Read the list of users in YouTrack.

        https://www.jetbrains.com/help/youtrack/devportal/resource-api-users.html#get_all-User-method
        """
        return parse_obj_as(
            tuple[User, ...],
            self._get(
                path="/users",
                fields=model_to_field_names(User),
                offset=offset,
                count=count,
            ),
        )
