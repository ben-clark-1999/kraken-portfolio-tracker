def format_aud(value: float) -> str:
    """Format a float as AUD string: '$1,234.56'"""
    return f"${value:,.2f}"


def format_pct(value: float) -> str:
    """Format as percentage string: '42.31%'"""
    return f"{value:.2f}%"
