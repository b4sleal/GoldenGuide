"""Undergraduate or graduate: which Academic Calendar a page or course belongs to.

Records without a level (NULL) are not level-specific, such as tuition, important dates and other
university website pages: they apply to every student.
"""
from enum import StrEnum


class AcademicLevel(StrEnum):
    UNDERGRADUATE = "undergraduate"
    GRADUATE = "graduate"
