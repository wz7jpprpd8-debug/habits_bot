from collections import Counter
from datetime import timedelta

def analyze_logs(dates):
    weekdays = Counter(d.weekday() for d in dates)
    streaks = []
    current = 1

    for i in range(1, len(dates)):
        if dates[i] == dates[i-1] + timedelta(days=1):
            current += 1
        else:
            streaks.append(current)
            current = 1
    streaks.append(current)

    return {
        "total": len(dates),
        "best_weekday": weekdays.most_common(1)[0][0],
        "worst_weekday": weekdays.most_common()[-1][0],
        "avg_streak": sum(streaks) / len(streaks),
        "max_streak": max(streaks)
    }
