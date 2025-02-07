from datetime import datetime, timedelta


def calculate_priority(inlet_level, max_capacity):
    """Calculate priority based on percentage fill.
    
    Returns a higher value (lower priority) for lower percentages.
    """
    return (1 - (inlet_level / max_capacity)) * 100


def travel_time(distance, speed):
    return distance / speed


def convert_to_time(minutes):
    minutes = int(minutes)
    rounded_minutes = (minutes // 1)
    hours = rounded_minutes // 60
    minutes = rounded_minutes % 60
    hours = hours % 24  # Wrap hours within 0-23 range
    return f"{hours:02d}:{minutes:02d}"


def minutes_to_time(minutes):
    if minutes == 'Time [hh:mm]':
        return minutes
    time = datetime(2023, 1, 1) + timedelta(minutes=minutes)
    return time.strftime('%H:%M')


def minutes_to_day(minutes):
    if minutes == 'Time [hh:mm]':
        return 'Time [Day]'
    day, _ = divmod(minutes, 24 * 60)
    return day


def minutes_to_weekday(minutes):
    minutes = int(minutes)
    if minutes == 'Time [hh:mm]':
        return 'Time [Weekday]'
    weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    day = ((minutes // (24 * 60)) % 7) + 1
    return weekdays[day - 1]


def get_time_to_next_start(env, array_of_starts):
    result = 24 * 60 + 1
    _, minute = divmod(env.now, 24*60)
    for starts in array_of_starts:
        for start_time in starts:
            if minute <= start_time:
                difference = start_time - minute
                if difference < result:
                    result = difference
    
    if result >= 24*60:
        for starts in array_of_starts:
            for start_time in starts:
                if minute <= start_time + 24 * 60:
                    difference = start_time + 24 * 60 - minute
                    if difference < result:
                        result = difference

    return result - 1

class Time:
    MINUTES_PER_DAY = 24 * 60
    DAYS_PER_WEEK = 7
    WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

    def __init__(self, total_minutes):
        self.total_minutes = total_minutes
        self.days, self.minute_of_day = divmod(total_minutes, self.MINUTES_PER_DAY)
        self.week_number = (self.days // self.DAYS_PER_WEEK) % 2  # 0=Even week, 1=Odd week
        self.day_of_week = self.days % self.DAYS_PER_WEEK  # 0=Monday, 6=Sunday
        self.hour = self.minute_of_day // 60
        self.minute = self.minute_of_day % 60

    def to_hhmm(self):
        return f"{self.hour:02d}:{self.minute:02d}"

    def to_day(self):
        return self.days

    def to_weekday(self):
        return self.WEEKDAYS[self.day_of_week]

    def is_workday(self, saturday_op, sunday_op):
        if self.day_of_week < 5:  # Weekday
            return True
        elif self.day_of_week == 5:  # Saturday
            return saturday_op == 'WEEKLY' or (saturday_op == 'BI-WEEKLY' and self.week_number == 0)
        elif self.day_of_week == 6:  # Sunday
            return sunday_op == 'WEEKLY' or (sunday_op == 'BI-WEEKLY' and self.week_number == 0)

    def time_until_next_start(self, start_schedules):
        min_delta = float('inf')
        for schedule in start_schedules:
            for start_time in schedule:
                if self.minute_of_day <= start_time:
                    delta = start_time - self.minute_of_day
                else:
                    delta = (self.MINUTES_PER_DAY - self.minute_of_day) + start_time
                if delta < min_delta:
                    min_delta = delta
        return min_delta if min_delta != float('inf') else 0
   