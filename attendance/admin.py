from django.contrib import admin
from .models import (
    AttendanceRecord, Holiday, TimesheetActivity,
    CompOffRecord, TimesheetRecord, LeaveBalance, UserEarningsConfig,
)

@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "check_in", "check_out", "leave_type", "work_location", "is_holiday")
    list_filter  = ("is_holiday", "leave_type", "work_location")
    search_fields = ("user__username",)

@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ("date", "name")

@admin.register(TimesheetActivity)
class TimesheetActivityAdmin(admin.ModelAdmin):
    list_display = ("user", "year", "month", "srno", "activity", "sub_activity")
    list_filter  = ("year", "month")

@admin.register(CompOffRecord)
class CompOffRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "worked_date", "leave_date", "status")
    list_filter  = ("status",)

@admin.register(TimesheetRecord)
class TimesheetRecordAdmin(admin.ModelAdmin):
    list_display = ("attendance_record", "ts_check_in", "ts_check_out")

@admin.register(LeaveBalance)
class LeaveBalanceAdmin(admin.ModelAdmin):
    list_display  = ("user", "year", "leave_type", "total_entitled", "carried_over", "used", "available")
    list_filter   = ("year", "leave_type")
    search_fields = ("user__username",)
    readonly_fields = ("available",)

    def available(self, obj):
        return obj.available
    available.short_description = "Available"

@admin.register(UserEarningsConfig)
class UserEarningsConfigAdmin(admin.ModelAdmin):
    list_display = ("user", "daily_rate", "saturday_mode", "saturday_rate")
