import logging
import os
import paramiko
from django.conf import settings
from datetime import datetime

logger = logging.getLogger("attendance")

def grant_monthly_leave():
    """
    Runs on the 1st of every month.
    Adds 1.0 Sick Leave and 1.5 Earned Leave to every active user's balance
    for the current year.
    """
    from django.contrib.auth.models import User
    from attendance.models import LeaveBalance

    today = datetime.today()
    year = today.year

    SL_MONTHLY = 1.0
    EL_MONTHLY = 1.5

    users = User.objects.filter(is_active=True)
    for user in users:
        # Sick Leave
        sl, _ = LeaveBalance.objects.get_or_create(
            user=user, year=year, leave_type="sick",
            defaults={"total_entitled": 0.0, "used": 0.0, "carried_over": 0.0}
        )
        sl.total_entitled = round(sl.total_entitled + SL_MONTHLY, 2)
        sl.save()

        # Earned Leave
        el, _ = LeaveBalance.objects.get_or_create(
            user=user, year=year, leave_type="earned",
            defaults={"total_entitled": 0.0, "used": 0.0, "carried_over": 0.0}
        )
        el.total_entitled = round(el.total_entitled + EL_MONTHLY, 2)
        el.save()

        logger.info(
            "Monthly leave granted to %s: +%.1f SL, +%.1f EL (year %d)",
            user.username, SL_MONTHLY, EL_MONTHLY, year
        )

    logger.info("Monthly leave accrual complete for %d users.", users.count())

def backup_db_to_sftp():
    """
    Backs up the SQLite database to a remote SFTP server.
    """
    db_path = os.path.join(settings.BASE_DIR, "db.sqlite3")
    if not os.path.exists(db_path):
        logger.error("SFTP Backup: db.sqlite3 not found at %s", db_path)
        return

    host = settings.SFTP_HOST
    port = settings.SFTP_PORT
    user = settings.SFTP_USER
    password = settings.SFTP_PASS
    remote_dir = settings.SFTP_REMOTE_DIR

    if not host or not user:
        logger.warning("SFTP Backup: Host or User not configured. Skipping backup.")
        return

    try:
        transport = paramiko.Transport((host, port))
        transport.connect(username=user, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)

        # Ensure remote directory exists
        try:
            sftp.chdir(remote_dir)
        except IOError:
            sftp.mkdir(remote_dir)
            sftp.chdir(remote_dir)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        remote_filename = f"db_backup_{timestamp}.sqlite3"

        logger.info("SFTP Backup: Uploading %s to %s", db_path, remote_filename)
        sftp.put(db_path, remote_filename)

        sftp.close()
        transport.close()
        logger.info("SFTP Backup: Successfully uploaded %s", remote_filename)

    except Exception as e:
        logger.error("SFTP Backup Error: %s", str(e))

def send_daily_summary_report():
    """
    Placeholder for a daily summary report email.
    """
    logger.info("Task: Sending daily summary report (Placeholder)")
    # Logic to send email would go here
    pass
