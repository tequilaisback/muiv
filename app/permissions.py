from __future__ import annotations

from typing import List, Optional

from .models import (
    ROLE_ADMIN,
    ROLE_COACH,
    ROLE_DOCTOR,
    ROLE_OPERATOR,
    ROLE_USER,
    Team,
    User,
)


def _is_active_user(user: Optional[User]) -> bool:
    return bool(user and getattr(user, "is_authenticated", False) and getattr(user, "is_active", True))


def has_role(user: Optional[User], *roles: str) -> bool:
    if not _is_active_user(user):
        return False
    return bool(getattr(user, "has_role", lambda *_: False)(*roles))


def is_admin(user: Optional[User]) -> bool:
    return has_role(user, ROLE_ADMIN)


def is_doctor(user: Optional[User]) -> bool:
    return has_role(user, ROLE_DOCTOR)


def is_coach(user: Optional[User]) -> bool:
    return has_role(user, ROLE_COACH)


def is_operator(user: Optional[User]) -> bool:
    return has_role(user, ROLE_OPERATOR)


def is_user(user: Optional[User]) -> bool:
    return has_role(user, ROLE_USER)


def is_staff(user: Optional[User]) -> bool:
    return has_role(user, ROLE_ADMIN, ROLE_DOCTOR, ROLE_COACH, ROLE_OPERATOR)


def get_coach_teams(user: Optional[User]) -> List[Team]:
    if not is_coach(user):
        return []
    return Team.query.filter_by(coach_id=user.id).all()


def get_coach_team_ids(user: Optional[User]) -> List[int]:
    return [t.id for t in get_coach_teams(user)]


def get_team_scope_ids(user: Optional[User]) -> Optional[List[int]]:
    """
    None = no restriction (all data).
    []  = explicit empty scope.
    """
    if not _is_active_user(user):
        return []
    if is_admin(user) or is_doctor(user) or is_operator(user):
        return None
    if is_coach(user):
        team_ids = get_coach_team_ids(user)
        return team_ids or None
    return []
