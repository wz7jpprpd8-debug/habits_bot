import matplotlib.pyplot as plt
from datetime import date, timedelta
import tempfile

def habit_progress_chart(title, dates):
    today = date.today()
    days = [today - timedelta(days=i) for i in reversed(range(30))]
    values = [1 if str(d) in dates else 0 for d in days]

    plt.figure()
    plt.plot(days, values)
    plt.ylim(0, 1.2)
    plt.title(title)
    plt.grid(True)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    plt.savefig(tmp.name)
    plt.close()

    return tmp.name
