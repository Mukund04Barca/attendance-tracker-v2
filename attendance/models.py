from django.db import models
from django.contrib.auth.models import User


class Holiday(models.Model):
    date = models.DateField(unique=True)
    name = models.CharField(max_length=100)

    def __str__(self) -> str:
        return f"{self.date} - {self.name}"


class AttendanceRecord(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)
    ts_check_in = models.DateTimeField(null=True, blank=True)
    ts_check_out = models.DateTimeField(null=True, blank=True)
    is_holiday = models.BooleanField(default=False)
    allowance_hours = models.FloatField(default=0.0)
    leave_type = models.CharField(max_length=50, null=True, blank=True)
    # WFH / office tagging
    work_location = models.CharField(
        max_length=20,
        choices=[("office", "Office"), ("wfh", "WFH"), ("client", "Client Site")],
        default="office",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "date")
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"{self.user.username} - {self.date}"


class TimesheetRecord(models.Model):
    """Derived timesheet data separate from source AttendanceRecord."""
    attendance_record = models.OneToOneField(
        AttendanceRecord,
        on_delete=models.CASCADE,
        related_name="timesheet_derived",
    )
    ts_check_in = models.DateTimeField(null=True, blank=True)
    ts_check_out = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Timesheet for {self.attendance_record.date} ({self.attendance_record.user.username})"


class TimesheetActivity(models.Model):
    """Stores a single task/activity row for the NSE Timesheet for a given user & month."""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    year = models.IntegerField()
    month = models.IntegerField()  # 1-12
    srno = models.IntegerField(default=1)
    activity = models.CharField(max_length=200, blank=True, default="")
    sub_activity = models.TextField(blank=True, default="")
    comments = models.TextField(blank=True, default="")
    artifact_id = models.CharField(max_length=100, blank=True, default="")
    # Daily hours stored as JSON: {"1": 4.5, "15": 9, ...}
    daily_hours = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["srno", "id"]

    def __str__(self) -> str:
        return f"{self.user.username} - {self.year}/{self.month} - {self.activity}"


class CompOffRecord(models.Model):
    """Tracks a compensation-off entitlement when an employee works on Saturday."""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    worked_date = models.DateField()
    leave_date = models.DateField(null=True, blank=True)
    reason = models.CharField(max_length=300, blank=True, default="")
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("consumed", "Consumed"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "worked_date")
        ordering = ["-worked_date"]

    def __str__(self) -> str:
        return f"{self.user.username} comp-off for {self.worked_date} (status: {self.status})"


class LeaveBalance(models.Model):
    """
    Tracks leave balances per user per year.
    Balances auto-increment at the start of each year.
    """
    LEAVE_TYPES = [
        ("casual", "Casual Leave"),
        ("earned", "Earned Leave"),
        ("sick", "Sick Leave"),
        ("paternity", "Paternity Leave"),
        ("loss_of_pay", "Loss of Pay"),
        ("comp_off", "Compensatory Off"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    year = models.IntegerField()
    leave_type = models.CharField(max_length=30, choices=LEAVE_TYPES)

    # Entitlement for the year (editable by admin / auto-set)
    total_entitled = models.FloatField(default=0.0)
    # Used so far this year
    used = models.FloatField(default=0.0)
    # Carried over from previous year
    carried_over = models.FloatField(default=0.0)

    class Meta:
        unique_together = ("user", "year", "leave_type")
        ordering = ["leave_type"]

    @property
    def available(self):
        return round(self.total_entitled + self.carried_over - self.used, 2)

    def __str__(self) -> str:
        return f"{self.user.username} - {self.leave_type} ({self.year}): {self.available} left"


class UserEarningsConfig(models.Model):
    """Per-user earnings configuration."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="earnings_config")
    # Daily earnings (weekday)
    daily_rate = models.FloatField(default=250.0, help_text="Earnings per weekday (₹)")
    # Saturday: either comp_off or pay
    saturday_mode = models.CharField(
        max_length=10,
        choices=[("pay", "Pay"), ("comp_off", "Comp-Off")],
        default="pay",
        help_text="Saturday work: receive pay or comp-off?",
    )
    saturday_rate = models.FloatField(default=250.0, help_text="Earnings per Saturday if mode=pay (₹)")

    def __str__(self) -> str:
        return f"{self.user.username} earnings config"
