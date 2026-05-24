from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("attendance", "0007_timesheetrecord"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Add work_location to AttendanceRecord
        migrations.AddField(
            model_name="attendancerecord",
            name="work_location",
            field=models.CharField(
                choices=[("office", "Office"), ("wfh", "WFH"), ("client", "Client Site")],
                default="office",
                max_length=20,
            ),
        ),
        # LeaveBalance
        migrations.CreateModel(
            name="LeaveBalance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("year", models.IntegerField()),
                ("leave_type", models.CharField(
                    choices=[
                        ("casual", "Casual Leave"),
                        ("earned", "Earned Leave"),
                        ("sick", "Sick Leave"),
                        ("paternity", "Paternity Leave"),
                        ("loss_of_pay", "Loss of Pay"),
                        ("comp_off", "Compensatory Off"),
                    ],
                    max_length=30,
                )),
                ("total_entitled", models.FloatField(default=0.0)),
                ("used", models.FloatField(default=0.0)),
                ("carried_over", models.FloatField(default=0.0)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["leave_type"], "unique_together": {("user", "year", "leave_type")}},
        ),
        # UserEarningsConfig
        migrations.CreateModel(
            name="UserEarningsConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("daily_rate", models.FloatField(default=250.0)),
                ("saturday_mode", models.CharField(
                    choices=[("pay", "Pay"), ("comp_off", "Comp-Off")],
                    default="pay",
                    max_length=10,
                )),
                ("saturday_rate", models.FloatField(default=250.0)),
                ("user", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="earnings_config",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),
    ]
