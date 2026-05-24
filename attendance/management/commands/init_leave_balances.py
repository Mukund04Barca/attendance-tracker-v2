"""
Management command: python manage.py init_leave_balances [--year YYYY]

Run once per year (e.g. via cron on Jan 1) to:
  1. Create LeaveBalance rows for all users for the given year.
  2. Carry over unused Earned Leave from the previous year (up to 30 days max).
  3. Grant monthly Earned Leave accrual (1.25 days / month = 15 / year).

Usage:
    python manage.py init_leave_balances             # current year
    python manage.py init_leave_balances --year 2027
"""

from datetime import date
import logging

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from attendance.models import LeaveBalance
from attendance.views import DEFAULT_LEAVE_ENTITLEMENTS

logger = logging.getLogger("attendance")

EARNED_LEAVE_ANNUAL    = 15.0   # days entitled per year
EARNED_LEAVE_CARRYOVER = 30.0   # max carry-over cap


class Command(BaseCommand):
    help = "Initialise / roll-over leave balances for a given year."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, default=date.today().year)

    def handle(self, *args, **options):
        year     = options["year"]
        prev_year = year - 1
        users    = User.objects.filter(is_active=True)

        created_count  = 0
        rollover_count = 0

        for user in users:
            for lt, entitled in DEFAULT_LEAVE_ENTITLEMENTS.items():
                # Carry over earned leave from previous year
                carry = 0.0
                if lt == "earned":
                    try:
                        prev = LeaveBalance.objects.get(user=user, year=prev_year, leave_type="earned")
                        carry = min(max(prev.available, 0), EARNED_LEAVE_CARRYOVER)
                    except LeaveBalance.DoesNotExist:
                        pass
                    entitled = EARNED_LEAVE_ANNUAL

                _, created = LeaveBalance.objects.get_or_create(
                    user=user,
                    year=year,
                    leave_type=lt,
                    defaults={"total_entitled": entitled, "carried_over": carry},
                )
                if created:
                    created_count += 1
                    if carry > 0:
                        rollover_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Year {year}: {created_count} leave balance rows created, {rollover_count} with earned-leave carry-over."
        ))
