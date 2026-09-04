import json
from unittest.mock import MagicMock, patch

import pytest
from requests.exceptions import HTTPError, Timeout

from src.components.email_service.services import TalkoEmailService


def make_service(**overrides):
    """Return an TalkoEmailService with safe defaults and a mock logger."""
    logger = MagicMock()
    template_env = MagicMock()
    defaults = dict(
        logger=logger,
        api_url="https://email.example.com/send",
        channel_key="default-channel-key",
        sender_email="sender@example.com",
        template_env=template_env,
    )
    defaults.update(overrides)
    svc = TalkoEmailService(**defaults)
    return svc, logger, template_env


VALID_TO = ["alice@example.com"]
VALID_SUBJECT = "Hello"
VALID_BODY = "Plain text body"


class TestValidateEmails:

    def test_raises_on_empty_list(self):
        svc, logger, _ = make_service()
        with pytest.raises(ValueError, match="To"):
            svc._validate_emails([], "To")
        logger.error.assert_called_once()

    def test_raises_on_invalid_email(self):
        svc, logger, _ = make_service()
        with pytest.raises(ValueError, match="To"):
            svc._validate_emails(["not-an-email"], "To")
        logger.error.assert_called_once()

    def test_passes_on_valid_emails(self):
        svc, logger, _ = make_service()
        svc._validate_emails(["a@b.com", "c@d.org"], "To")  # no exception
        logger.error.assert_not_called()

    def test_label_appears_in_error_message(self):
        svc, _, _ = make_service()
        with pytest.raises(ValueError) as exc_info:
            svc._validate_emails(["bad"], "BCC")
        assert "BCC" in str(exc_info.value)


class TestRenderHtmlContent:

    def test_returns_none_when_no_template(self):
        svc, _, _ = make_service()
        result = svc._render_html_content("body", html_template=None)
        assert result is None

    def test_renders_string_body(self):
        svc, _, template_env = make_service()
        mock_template = MagicMock()
        mock_template.render.return_value = "<p>hello</p>"
        template_env.get_template.return_value = mock_template

        result = svc._render_html_content("hello", html_template="tpl.html")

        template_env.get_template.assert_called_once_with("tpl.html")
        mock_template.render.assert_called_once_with(body="hello")
        assert result == "<p>hello</p>"

    def test_renders_dict_body_as_kwargs(self):
        svc, _, template_env = make_service()
        mock_template = MagicMock()
        mock_template.render.return_value = "<p>rendered</p>"
        template_env.get_template.return_value = mock_template

        svc._render_html_content({"name": "Alice"}, html_template="tpl.html")

        mock_template.render.assert_called_once_with(name="Alice")

    def test_raises_and_logs_on_template_error(self):
        svc, logger, template_env = make_service()
        template_env.get_template.side_effect = Exception("template not found")

        with pytest.raises(Exception, match="template not found"):
            svc._render_html_content("body", html_template="missing.html")
        logger.error.assert_called_once()


class TestValidateInputs:

    def test_raises_on_empty_subject(self):
        svc, logger, _ = make_service()
        with pytest.raises(ValueError):
            svc._validate_inputs(VALID_TO, "", VALID_BODY, None, None)
        logger.error.assert_called()

    def test_raises_on_non_string_subject(self):
        svc, _, _ = make_service()
        with pytest.raises(ValueError):
            svc._validate_inputs(VALID_TO, 123, VALID_BODY, None, None)

    def test_raises_on_empty_body(self):
        svc, logger, _ = make_service()
        with pytest.raises(ValueError):
            svc._validate_inputs(VALID_TO, VALID_SUBJECT, "", None, None)
        logger.error.assert_called()

    def test_raises_on_invalid_cc(self):
        svc, _, _ = make_service()
        with pytest.raises(ValueError, match="CC"):
            svc._validate_inputs(
                VALID_TO, VALID_SUBJECT, VALID_BODY, ["bad-email"], None
            )

    def test_raises_on_invalid_bcc(self):
        svc, _, _ = make_service()
        with pytest.raises(ValueError, match="BCC"):
            svc._validate_inputs(
                VALID_TO, VALID_SUBJECT, VALID_BODY, None, ["bad-email"]
            )

    def test_skips_cc_bcc_validation_when_none(self):
        svc, _, _ = make_service()
        svc._validate_inputs(
            VALID_TO, VALID_SUBJECT, VALID_BODY, None, None
        )  # no exception


class TestBuildPayload:

    def test_basic_payload_structure(self):
        svc, _, _ = make_service()
        payload = svc._build_payload(
            VALID_TO, VALID_SUBJECT, VALID_BODY, None, None, None, None
        )
        assert payload["to_emails"] == VALID_TO
        assert payload["subject"] == VALID_SUBJECT
        assert payload["body"] == VALID_BODY
        assert payload["cc_emails"] == []
        assert payload["bcc_emails"] == []
        assert "html_content" not in payload
        assert "attachments" not in payload

    def test_dict_body_is_json_serialized(self):
        svc, _, _ = make_service()
        body_dict = {"key": "value"}
        payload = svc._build_payload(
            VALID_TO, VALID_SUBJECT, body_dict, None, None, None, None
        )
        assert payload["body"] == json.dumps(body_dict)

    def test_html_content_added_when_template_provided(self):
        svc, _, template_env = make_service()
        mock_template = MagicMock()
        mock_template.render.return_value = "<h1>hi</h1>"
        template_env.get_template.return_value = mock_template

        payload = svc._build_payload(
            VALID_TO, VALID_SUBJECT, VALID_BODY, None, None, "tpl.html", None
        )
        assert payload["html_content"] == "<h1>hi</h1>"

    def test_attachments_added_when_provided(self):
        svc, _, _ = make_service()
        attachments = [{"filename": "file.pdf", "content": "base64data"}]
        payload = svc._build_payload(
            VALID_TO, VALID_SUBJECT, VALID_BODY, None, None, None, attachments
        )
        assert payload["attachments"] == attachments

    def test_cc_and_bcc_included(self):
        svc, _, _ = make_service()
        payload = svc._build_payload(
            VALID_TO,
            VALID_SUBJECT,
            VALID_BODY,
            ["cc@example.com"],
            ["bcc@example.com"],
            None,
            None,
        )
        assert payload["cc_emails"] == ["cc@example.com"]
        assert payload["bcc_emails"] == ["bcc@example.com"]


class TestMakeApiCall:

    def _mock_response(self, status_code=200, json_data=None, raise_for_status=None):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_data or {"task_id": "abc123"}
        if raise_for_status:
            resp.raise_for_status.side_effect = raise_for_status
        else:
            resp.raise_for_status.return_value = None
        return resp

    @patch("src.components.email_service.services.requests.post")
    def test_successful_call_returns_json(self, mock_post):
        svc, logger, _ = make_service()
        mock_post.return_value = self._mock_response(json_data={"task_id": "xyz"})

        result = svc._make_api_call({"to_emails": VALID_TO})
        assert result == {"task_id": "xyz"}
        logger.info.assert_called()

    @patch("src.components.email_service.services.requests.post")
    def test_uses_default_channel_key(self, mock_post):
        svc, _, _ = make_service(channel_key="my-key")
        mock_post.return_value = self._mock_response()

        svc._make_api_call({"to_emails": VALID_TO})
        _, kwargs = mock_post.call_args
        assert kwargs["headers"]["X-Channel-Key"] == "my-key"

    @patch("src.components.email_service.services.requests.post")
    def test_overrides_channel_key_when_provided(self, mock_post):
        svc, _, _ = make_service(channel_key="default-key")
        mock_post.return_value = self._mock_response()

        svc._make_api_call({"to_emails": VALID_TO}, channel_key="override-key")
        _, kwargs = mock_post.call_args
        assert kwargs["headers"]["X-Channel-Key"] == "override-key"

    @patch("src.components.email_service.services.requests.post")
    def test_retries_3_times_then_raises(self, mock_post):
        svc, logger, _ = make_service()
        mock_post.side_effect = Timeout("timed out")

        with pytest.raises(ValueError, match="timed out"):
            svc._make_api_call({"to_emails": VALID_TO})

        assert mock_post.call_count == 3
        assert logger.warning.call_count == 3
        logger.error.assert_called_once()

    @patch("src.components.email_service.services.requests.post")
    def test_raises_on_http_error_after_retries(self, mock_post):
        svc, _, _ = make_service()
        resp = self._mock_response(raise_for_status=HTTPError("500 Server Error"))
        mock_post.return_value = resp

        with pytest.raises(ValueError):
            svc._make_api_call({"to_emails": VALID_TO})
        assert mock_post.call_count == 3

    @patch("src.components.email_service.services.requests.post")
    def test_succeeds_on_second_attempt(self, mock_post):
        svc, logger, _ = make_service()
        self._mock_response(raise_for_status=Timeout("timeout"))
        ok_resp = self._mock_response(json_data={"task_id": "retry-ok"})
        mock_post.side_effect = [Timeout("timeout"), ok_resp]

        result = svc._make_api_call({"to_emails": VALID_TO})

        assert result == {"task_id": "retry-ok"}
        assert mock_post.call_count == 2
        assert logger.warning.call_count == 1


class TestSendEmail:

    @patch("src.components.email_service.services.requests.post")
    def test_full_happy_path(self, mock_post):
        svc, logger, _ = make_service()
        mock_post.return_value = MagicMock(
            status_code=200,
            raise_for_status=MagicMock(return_value=None),
            json=MagicMock(return_value={"task_id": "done"}),
        )

        result = svc.send_email(
            to_emails=VALID_TO,
            subject=VALID_SUBJECT,
            body=VALID_BODY,
        )
        assert result["task_id"] == "done"
        logger.info.assert_called()

    @patch("src.components.email_service.services.requests.post")
    def test_send_email_with_all_optional_fields(self, mock_post):
        svc, _, template_env = make_service()
        mock_template = MagicMock()
        mock_template.render.return_value = "<p>body</p>"
        template_env.get_template.return_value = mock_template
        mock_post.return_value = MagicMock(
            raise_for_status=MagicMock(return_value=None),
            json=MagicMock(return_value={"task_id": "full"}),
        )

        result = svc.send_email(
            to_emails=VALID_TO,
            subject=VALID_SUBJECT,
            body=VALID_BODY,
            cc_emails=["cc@example.com"],
            bcc_emails=["bcc@example.com"],
            html_template="tpl.html",
            attachments=[{"filename": "a.pdf", "content": "data"}],
            channel_key="custom-key",
        )
        assert result["task_id"] == "full"
        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        assert "html_content" in payload
        assert "attachments" in payload
        assert kwargs["headers"]["X-Channel-Key"] == "custom-key"

    def test_send_email_raises_on_invalid_to(self):
        svc, _, _ = make_service()
        with pytest.raises(ValueError):
            svc.send_email(to_emails=["bad"], subject=VALID_SUBJECT, body=VALID_BODY)

    def test_send_email_raises_on_empty_subject(self):
        svc, _, _ = make_service()
        with pytest.raises(ValueError):
            svc.send_email(to_emails=VALID_TO, subject="", body=VALID_BODY)

    def test_send_email_raises_on_empty_body(self):
        svc, _, _ = make_service()
        with pytest.raises(ValueError):
            svc.send_email(to_emails=VALID_TO, subject=VALID_SUBJECT, body="")
