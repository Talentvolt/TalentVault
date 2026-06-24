def format_salary_lpa(value):
    if value is None or value == 0:
        return "0 LPA"
    try:
        val = float(value)
        lpa = val / 100000.0
        if lpa.is_integer():
            return f"{int(lpa)} LPA"
        else:
            s = f"{lpa:.2f}"
            if s.endswith('.00'):
                return f"{int(lpa)} LPA"
            elif s.endswith('0'):
                return f"{s[:-1]} LPA"
            else:
                return f"{s} LPA"
    except (ValueError, TypeError):
        return str(value)
