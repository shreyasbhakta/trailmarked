"""In-memory member/sub-account data for the mock bank app, one set per tenant."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Member:
    member_id: str
    name: str
    balance_cents: int
    status: str = "active"  # active | restricted (drives permission-denied)


@dataclass
class SubAccount:
    sub_account_id: str
    member_id: str
    account_type: str
    nickname: str
    opening_deposit_cents: int


@dataclass
class TenantData:
    members: dict[str, Member]
    sub_accounts: dict[str, SubAccount] = field(default_factory=dict)
    next_sub_account_seq: int = 1000


def _seed(tenant_label: str) -> TenantData:
    return TenantData(
        members={
            "1001": Member("1001", f"Alice Nguyen ({tenant_label})", 482_311),
            "1002": Member("1002", f"Marcus Reyes ({tenant_label})", 12_450),
            "1003": Member("1003", f"Priya Shah ({tenant_label})", 990_002),
            "9403": Member("9403", f"Restricted Holder ({tenant_label})", 0, status="restricted"),
        }
    )


TENANTS: dict[str, TenantData] = {
    "default": _seed("Default Branch"),
    "overlay_demo": _seed("Overlay Branch"),
}


def get_tenant(tenant_id: str) -> TenantData:
    if tenant_id not in TENANTS:
        raise KeyError(tenant_id)
    return TENANTS[tenant_id]


def next_sub_account_id(tenant: TenantData) -> str:
    tenant.next_sub_account_seq += 1
    return f"SUB-{tenant.next_sub_account_seq}"
