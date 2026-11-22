"""Тип пространства в данных синхронизации и в графе OpenFGA."""

from enum import StrEnum


class SpaceType(StrEnum):
    """Значения space_type, которые принимает auth-service."""

    PERSONAL = "personal"
    SHARED = "shared"
