import pytest

from cancer_claw.services.identity import mail


def test_mail_not_configured_by_default(monkeypatch):
    monkeypatch.setattr(mail.settings.mail, "host", "")
    monkeypatch.setattr(mail.settings.mail, "from_addr", "")
    assert not mail.is_mail_configured()


def test_mail_configured_when_host_and_from(monkeypatch):
    monkeypatch.setattr(mail.settings.mail, "host", "smtp.example.com")
    monkeypatch.setattr(mail.settings.mail, "from_addr", "no-reply@example.com")
    assert mail.is_mail_configured()


def test_send_email_requires_config(monkeypatch):
    monkeypatch.setattr(mail.settings.mail, "host", "")
    with pytest.raises(mail.MailError):
        mail._send("a@b.c", "s", "t")
