from enum import StrEnum


class Role(StrEnum):
    SUPER_ADMIN = "SUPER_ADMIN"
    STATE_ADMIN = "STATE_ADMIN"
    DISTRICT_ADMIN = "DISTRICT_ADMIN"
    LM_OFFICER = "LM_OFFICER"
    GATC = "GATC"
    BUSINESS = "BUSINESS"


class OrgType(StrEnum):
    BUSINESS = "BUSINESS"
    GATC = "GATC"


# Used only for user management (who may manage whom). It never grants permissions:
# every endpoint lists its allowed roles explicitly.
ROLE_RANK: dict[Role, int] = {
    Role.SUPER_ADMIN: 60,
    Role.STATE_ADMIN: 50,
    Role.DISTRICT_ADMIN: 40,
    Role.LM_OFFICER: 30,
    Role.GATC: 20,
    Role.BUSINESS: 10,
}

ORG_ROLES: frozenset[Role] = frozenset({Role.BUSINESS, Role.GATC})
ADMIN_ROLES: frozenset[Role] = frozenset({Role.SUPER_ADMIN, Role.STATE_ADMIN, Role.DISTRICT_ADMIN})
