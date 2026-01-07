
def habit_analysis_prompt(name, stats):
    days = ["Понедельник","Вторник","Среда","Четверг","Пятница","Суббота","Воскресенье"]

    return f"""
Ты коуч по привычкам.
Дай 3–5 инсайтов и рекомендаций.

Привычка: {name}
Всего выполнений: {stats['total']}
Лучший день: {days[stats['best_weekday']]}
Худший день: {days[stats['worst_weekday']]}
Средний streak: {stats['avg_streak']:.1f}
Максимальный streak: {stats['max_streak']}
"""
