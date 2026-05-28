from rest_framework import serializers, viewsets, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.db import transaction
from datetime import date, datetime, timedelta
import calendar

from .models import (
    AttendanceRecord, Holiday, CompOffRecord,
    LeaveBalance, TimesheetActivity,
)
from django.contrib.auth.models import User
from django.conf import settings

ATT_CFG             = getattr(settings, "ATTENDANCE_CONFIG", {})
DAILY_TARGET_HOURS  = float(ATT_CFG.get("daily_hours_target",    9))
WEEKLY_TARGET       = float(ATT_CFG.get("weekly_hours_target",  45))
SATURDAY_TARGET     = float(ATT_CFG.get("saturday_hours_target", 6))
CONFIG_HOLIDAYS     = set(ATT_CFG.get("holidays", []))


def is_config_holiday(d):
    return d.isoformat() in CONFIG_HOLIDAYS


def _fmt_hhmm(decimal_hours):
    if decimal_hours is None:
        return "00:00"
    total_mins = int(round(abs(float(decimal_hours)) * 60))
    h = total_mins // 60
    m = total_mins % 60
    return f"{h:02d}:{m:02d}"


# ─────────────────────────────────────────────────────────
# SERIALIZERS
# ─────────────────────────────────────────────────────────

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email']


class AttendanceRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceRecord
        fields = ['id', 'date', 'check_in', 'check_out', 'is_holiday',
                  'leave_type', 'work_location', 'updated_at']
        read_only_fields = ['id', 'updated_at', 'is_holiday']


# ─────────────────────────────────────────────────────────
# PROFILE
# ─────────────────────────────────────────────────────────

class ProfileViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


# ─────────────────────────────────────────────────────────
# TODAY
# ─────────────────────────────────────────────────────────

class TodayAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        now   = timezone.localtime(timezone.now())
        today = now.date()

        is_holiday = Holiday.objects.filter(date=today).exists() or is_config_holiday(today)
        record, _ = AttendanceRecord.objects.get_or_create(
            user=request.user,
            date=today,
            defaults={"is_holiday": is_holiday},
        )

        check_in_display  = timezone.localtime(record.check_in).strftime("%H:%M")  if record.check_in  else None
        check_out_display = timezone.localtime(record.check_out).strftime("%H:%M") if record.check_out else None

        hours_today = None
        if record.check_in and record.check_out:
            delta = record.check_out - record.check_in
            hours_today = round(max(delta.total_seconds() / 3600.0, 0), 2)

        elapsed_display = None
        if record.check_in and not record.check_out:
            elapsed_secs = max((now - timezone.localtime(record.check_in)).total_seconds(), 0)
            elapsed_mins = int(round(elapsed_secs / 60.0))
            elapsed_display = f"{elapsed_mins // 60:02d}:{elapsed_mins % 60:02d}"

        week_start = today - timedelta(days=today.weekday())
        weekly_records = AttendanceRecord.objects.filter(
            user=request.user,
            date__range=(week_start, today),
            check_in__isnull=False,
            check_out__isnull=False,
        )
        weekly_total = sum(
            max((r.check_out - r.check_in).total_seconds() / 3600.0, 0)
            for r in weekly_records
        )

        return Response({
            "date":                 str(today),
            "is_holiday":           record.is_holiday,
            "is_leave":             bool(record.leave_type),
            "leave_type":           record.leave_type or "",
            "checked_in":           bool(record.check_in),
            "checked_out":          bool(record.check_out),
            "check_in":             check_in_display,
            "check_out":            check_out_display,
            "hours_today":          hours_today,
            "hours_display":        _fmt_hhmm(hours_today) if hours_today else None,
            "elapsed_display":      elapsed_display,
            "daily_target":         DAILY_TARGET_HOURS,
            "daily_target_display": _fmt_hhmm(DAILY_TARGET_HOURS),
            "weekly_total":         round(weekly_total, 2),
            "weekly_total_display": _fmt_hhmm(weekly_total),
            "weekly_target":        WEEKLY_TARGET,
        })

    def post(self, request):
        action = request.data.get("action")
        now    = timezone.localtime(timezone.now())
        today  = now.date()

        is_holiday = Holiday.objects.filter(date=today).exists() or is_config_holiday(today)
        record, _ = AttendanceRecord.objects.get_or_create(
            user=request.user,
            date=today,
            defaults={"is_holiday": is_holiday},
        )

        if action == "checkin":
            if record.check_in:
                return Response({"error": "Already checked in"}, status=400)
            record.check_in = now
            work_location = request.data.get("work_location", "office")
            if work_location in ("office", "wfh", "client"):
                record.work_location = work_location
            record.save()
            return Response({
                "status":   "checked_in",
                "check_in": timezone.localtime(record.check_in).strftime("%H:%M"),
            })

        elif action == "checkout":
            if not record.check_in:
                return Response({"error": "Not checked in yet"}, status=400)
            if record.check_out:
                return Response({"error": "Already checked out"}, status=400)
            record.check_out = now
            record.save()
            delta = record.check_out - record.check_in
            hours = round(max(delta.total_seconds() / 3600.0, 0), 2)
            return Response({
                "status":        "checked_out",
                "check_out":     timezone.localtime(record.check_out).strftime("%H:%M"),
                "hours":         hours,
                "hours_display": _fmt_hhmm(hours),
            })

        return Response({"error": "Invalid action. Use 'checkin' or 'checkout'"}, status=400)


# ─────────────────────────────────────────────────────────
# WEEKLY
# ─────────────────────────────────────────────────────────

class WeeklyAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today      = timezone.localtime(timezone.now()).date()
        start_date = today - timedelta(days=today.weekday())
        end_date   = start_date + timedelta(days=6)

        records = AttendanceRecord.objects.filter(
            user=request.user,
            date__range=(start_date, end_date),
        ).order_by("date")

        leave_dates = set(
            AttendanceRecord.objects.filter(
                user=request.user,
                date__range=(start_date, end_date),
            ).exclude(leave_type__isnull=True).exclude(leave_type="")
            .values_list("date", flat=True)
        )
        working_days = 0
        for i in range(7):
            d = start_date + timedelta(days=i)
            if d.weekday() >= 5:
                continue
            if Holiday.objects.filter(date=d).exists() or is_config_holiday(d):
                continue
            if d in leave_dates:
                continue
            working_days += 1
        weekly_target = round(working_days * DAILY_TARGET_HOURS, 2)

        rows = []
        weekly_total = 0.0
        for r in records:
            ci = timezone.localtime(r.check_in).strftime("%H:%M")  if r.check_in  else None
            co = timezone.localtime(r.check_out).strftime("%H:%M") if r.check_out else None
            hours = 0.0
            if r.check_in and r.check_out:
                hours = round(max((r.check_out - r.check_in).total_seconds() / 3600.0, 0), 2)
            weekly_total += hours

            variance = None
            if not r.is_holiday and not r.leave_type and ci:
                variance = round(hours - DAILY_TARGET_HOURS, 2)

            rows.append({
                "date":          str(r.date),
                "day":           r.date.strftime("%A"),
                "is_holiday":    r.is_holiday,
                "leave_type":    r.leave_type or "",
                "check_in":      ci,
                "check_out":     co,
                "hours":         hours,
                "hours_display": _fmt_hhmm(hours),
                "variance":      variance,
                "status": (
                    "HOLIDAY" if r.is_holiday else
                    "LEAVE"   if r.leave_type else
                    "MET"     if hours >= DAILY_TARGET_HOURS else
                    "SHORT"   if ci else
                    "ABSENT"
                ),
            })

        return Response({
            "week_start":            str(start_date),
            "week_end":              str(end_date),
            "weekly_target":         weekly_target,
            "weekly_target_display": _fmt_hhmm(weekly_target),
            "weekly_total":          round(weekly_total, 2),
            "weekly_total_display":  _fmt_hhmm(weekly_total),
            "days":                  rows,
        })


# ─────────────────────────────────────────────────────────
# MONTHLY
# ─────────────────────────────────────────────────────────

class MonthlyAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = timezone.localtime(timezone.now()).date()
        try:
            year  = int(request.query_params.get("year",  today.year))
            month = int(request.query_params.get("month", today.month))
        except (TypeError, ValueError):
            year, month = today.year, today.month

        records = AttendanceRecord.objects.filter(
            user=request.user, date__year=year, date__month=month
        )
        records_by_date = {}
        for r in records:
            ci = timezone.localtime(r.check_in).strftime("%H:%M")  if r.check_in  else None
            co = timezone.localtime(r.check_out).strftime("%H:%M") if r.check_out else None
            hours = 0.0
            if r.check_in and r.check_out:
                hours = round(max((r.check_out - r.check_in).total_seconds() / 3600.0, 0), 2)
            records_by_date[str(r.date)] = {
                "check_in":      ci,
                "check_out":     co,
                "hours":         hours,
                "hours_display": _fmt_hhmm(hours),
                "is_holiday":    r.is_holiday,
                "leave_type":    r.leave_type or "",
                "is_leave":      bool(r.leave_type),
            }

        holiday_dates = {
            str(h.date): h.name
            for h in Holiday.objects.filter(date__year=year, date__month=month)
        }

        _, days_in_month = calendar.monthrange(year, month)
        days = []
        for d in range(1, days_in_month + 1):
            day_date = date(year, month, d)
            day_str  = str(day_date)
            rec      = records_by_date.get(day_str, {})
            days.append({
                "date":         day_str,
                "day":          day_date.strftime("%A"),
                "is_weekend":   day_date.weekday() >= 5,
                "is_today":     day_date == today,
                "is_holiday":   day_str in holiday_dates or is_config_holiday(day_date),
                "holiday_name": holiday_dates.get(day_str, ""),
                **rec,
            })

        total_hours = round(sum(d.get("hours", 0) for d in days), 2)

        return Response({
            "year":                year,
            "month":               month,
            "month_name":          date(year, month, 1).strftime("%B %Y"),
            "total_hours":         total_hours,
            "total_hours_display": _fmt_hhmm(total_hours),
            "days":                days,
        })


# ─────────────────────────────────────────────────────────
# LEAVE
# ─────────────────────────────────────────────────────────

class LeaveAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today    = timezone.localtime(timezone.now()).date()
        balances = LeaveBalance.objects.filter(user=request.user, year=today.year)
        data = []
        for b in balances:
            data.append({
                "leave_type":   b.leave_type,
                "display":      b.get_leave_type_display(),
                "entitled":     b.total_entitled,
                "used":         b.used,
                "carried_over": b.carried_over,
                "available":    round(b.total_entitled + b.carried_over - b.used, 2),
            })
        return Response({"balances": data})

    def post(self, request):
        date_str   = request.data.get("date")
        leave_kind = request.data.get("leave_type", "Casual Leave")

        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return Response({"error": "Invalid date format. Use YYYY-MM-DD"}, status=400)

        valid_leave_types = [
            "Casual Leave", "Sick Leave", "Earned Leave",
            "Paternity Leave", "Loss of Pay", "Comp-Off"
        ]
        if leave_kind not in valid_leave_types:
            return Response({"error": f"Invalid leave type."}, status=400)

        record, _ = AttendanceRecord.objects.get_or_create(
            user=request.user,
            date=target_date,
            defaults={"is_holiday": Holiday.objects.filter(date=target_date).exists()},
        )
        record.check_in   = None
        record.check_out  = None
        record.leave_type = leave_kind
        record.save()

        leave_type_key = {
            "Casual Leave":    "casual",
            "Sick Leave":      "sick",
            "Earned Leave":    "earned",
            "Paternity Leave": "paternity",
            "Loss of Pay":     "loss_of_pay",
            "Comp-Off":        "comp_off",
        }.get(leave_kind)

        if leave_type_key:
            lb, _ = LeaveBalance.objects.get_or_create(
                user=request.user, year=target_date.year, leave_type=leave_type_key,
                defaults={"total_entitled": 0},
            )
            lb.used = round(lb.used + 1, 2)
            lb.save()

        return Response({
            "status":     "leave_marked",
            "date":       str(target_date),
            "leave_type": leave_kind,
        })


# ─────────────────────────────────────────────────────────
# EXISTING VIEWSET
# ─────────────────────────────────────────────────────────

class AttendanceRecordViewSet(viewsets.ModelViewSet):
    serializer_class   = AttendanceRecordSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return AttendanceRecord.objects.filter(user=self.request.user).order_by('-date')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['post'])
    def sync_records(self, request):
        records_data = request.data.get('records', [])
        synced_count = 0
        with transaction.atomic():
            for data in records_data:
                date_val = data.get('date')
                if not date_val:
                    continue
                record, _ = AttendanceRecord.objects.get_or_create(
                    user=request.user, date=date_val
                )
                client_updated_at = parse_datetime(data.get('updated_at', ''))
                if client_updated_at and record.updated_at:
                    if client_updated_at <= record.updated_at:
                        continue
                serializer = AttendanceRecordSerializer(record, data=data, partial=True)
                if serializer.is_valid():
                    serializer.save()
                    synced_count += 1
                else:
                    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response({'status': 'Sync successful', 'synced': synced_count})
