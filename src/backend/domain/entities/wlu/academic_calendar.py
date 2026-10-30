"""Academic Calendar vocabulary shared across entities: weekdays, seasons, course levels."""
from enum import IntEnum, StrEnum


class Weekday(StrEnum):
    """LORIS meeting-day keys (CourseMeetingTime day flags), in week order."""
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


class Season(StrEnum):
    """Academic terms as students name them. Spring, summer and intersession share one LORIS term code."""
    FALL = "fall"
    WINTER = "winter"
    SPRING = "spring"
    SUMMER = "summer"
    INTERSESSION = "intersession"


class CourseLevel(IntEnum):
    """A course number's first digit: 100-400 undergraduate, 500-800 graduate."""
    LEVEL_100 = 100
    LEVEL_200 = 200
    LEVEL_300 = 300
    LEVEL_400 = 400
    LEVEL_500 = 500
    LEVEL_600 = 600
    LEVEL_700 = 700
    LEVEL_800 = 800
