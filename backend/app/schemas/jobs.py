from pydantic import BaseModel


class ExpiryCheckSummary(BaseModel):
    checked: int
    reminders_30d_sent: int
    reminders_7d_sent: int
    expired: int
    email_failures: int
    skipped_no_recipient: int
