class TimesheetSessionMiddleware:
    """
    Extends session expiry to 8 hours when the user is on the timesheet page.
    All other pages keep the default short session (5 minutes).
    """
    TIMESHEET_MAX_AGE = 28800  # 8 hours in seconds

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if '/timesheet' in request.path:
            request.session.set_expiry(self.TIMESHEET_MAX_AGE)

        response = self.get_response(request)
        return response
