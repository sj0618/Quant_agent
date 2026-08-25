def build_signals(prices):
    """Return BUY/SELL/HOLD signals from close-price momentum."""
    signals = []
    previous_close = None
    for row in prices:
        close = float(row["close"])
        if previous_close is None:
            action = "HOLD"
        elif close > previous_close:
            action = "BUY"
        elif close < previous_close:
            action = "SELL"
        else:
            action = "HOLD"
        signals.append({"date": row["date"], "action": action, "price": close})
        previous_close = close
    return signals
