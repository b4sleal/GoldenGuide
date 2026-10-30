"""The shape every *FilterTranslator follows: apply(select, domain_filter) -> select."""
from typing import Protocol
from pydantic import BaseModel
from sqlalchemy import Select

class FilterTranslator(Protocol):
    """
    Infrastructure Contract: Defines the shape of any class
    that translates Pydantic Domain Filters into SQLAlchemy Select statements.
    """
    @staticmethod
    def apply(stmt: Select, filters: BaseModel) -> Select:
        ...