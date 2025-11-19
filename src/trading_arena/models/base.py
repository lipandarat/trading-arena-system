"""
Shared declarative base for all database models.

All models should import Base from this module to ensure they
use the same metadata registry.
"""

from sqlalchemy.orm import declarative_base

Base = declarative_base()