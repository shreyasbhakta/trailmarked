"""Deliberately legacy-feeling internal banking tool. Server-rendered HTML,
table/dl-based layout, no test IDs. Two tenants (default, overlay_demo) with
different markup for the same two flows, to give the capability registry's
tenant overlay something real to resolve against.

Failure injection, via the `inject` query param or special member IDs:
  - member_id "0000"        -> not-found
  - member_id "9403"        -> permission-denied (restricted holder)
  - ?inject=timeout         -> simulated timeout (slow response)
  - ?inject=notfound        -> not-found
  - ?inject=permission      -> permission-denied
  - sub-account form: empty nickname, non-numeric deposit, or negative
    deposit -> validation error
"""
from __future__ import annotations

import time

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from mock_bank_app.data import TENANTS, get_tenant, next_sub_account_id

app = FastAPI(title="Branch Teller System (mock)")

_TEMPLATE_ENGINES = {
    tenant_id: Jinja2Templates(directory=f"mock_bank_app/templates/{tenant_id}")
    for tenant_id in TENANTS
}

TIMEOUT_INJECTION_DELAY_S = 6


def _templates(tenant_id: str) -> Jinja2Templates:
    return _TEMPLATE_ENGINES[tenant_id]


def _error_page(request: Request, tenant_id: str, status_code: int, title: str, message: str) -> HTMLResponse:
    return _templates(tenant_id).TemplateResponse(
        request, "error.html", {"title": title, "message": message}, status_code=status_code
    )


@app.get("/{tenant_id}/members", response_class=HTMLResponse)
def search_page(request: Request, tenant_id: str, error: str | None = None):
    get_tenant(tenant_id)
    return _templates(tenant_id).TemplateResponse(request, "search.html", {"error": error})


@app.get("/{tenant_id}/members/lookup")
def lookup(tenant_id: str, member_id: str):
    return RedirectResponse(url=f"/{tenant_id}/members/{member_id}")


@app.get("/{tenant_id}/members/{member_id}", response_class=HTMLResponse)
def member_detail(request: Request, tenant_id: str, member_id: str, inject: str | None = None):
    tenant = get_tenant(tenant_id)

    if inject == "timeout":
        time.sleep(TIMEOUT_INJECTION_DELAY_S)
        return _error_page(request, tenant_id, 504, "Request Timed Out", "The teller backend did not respond in time.")

    if inject == "notfound" or member_id == "0000" or member_id not in tenant.members:
        return _error_page(request, tenant_id, 404, "Member Not Found", f"No member record for ID {member_id}.")

    member = tenant.members[member_id]

    if inject == "permission" or member.status == "restricted":
        return _error_page(request, tenant_id, 403, "Permission Denied", "This member record is restricted for your role.")

    balance_display = f"{member.balance_cents / 100:,.2f}"
    return _templates(tenant_id).TemplateResponse(
        request, "detail.html", {"member": member, "balance_display": balance_display}
    )


@app.get("/{tenant_id}/members/{member_id}/sub-accounts/new", response_class=HTMLResponse)
def sub_account_form(request: Request, tenant_id: str, member_id: str):
    get_tenant(tenant_id)
    return _templates(tenant_id).TemplateResponse(
        request, "sub_account_form.html", {"member_id": member_id, "errors": None, "form": {}}
    )


def _validate_sub_account_form(nickname: str, account_type: str, opening_deposit: str) -> tuple[list[str], int | None]:
    errors: list[str] = []
    if not nickname.strip():
        errors.append("Nickname is required.")
    if account_type not in ("savings", "checking"):
        errors.append("Account type must be savings or checking.")
    deposit_cents: int | None = None
    try:
        deposit_dollars = float(opening_deposit)
        if deposit_dollars < 0:
            errors.append("Opening deposit cannot be negative.")
        else:
            deposit_cents = round(deposit_dollars * 100)
    except ValueError:
        errors.append("Opening deposit must be a number.")
    return errors, deposit_cents


@app.post("/{tenant_id}/members/{member_id}/sub-accounts", response_class=HTMLResponse)
def create_sub_account(
    request: Request,
    tenant_id: str,
    member_id: str,
    nickname: str = Form(""),
    account_type: str = Form(""),
    opening_deposit: str = Form(""),
):
    tenant = get_tenant(tenant_id)
    if member_id not in tenant.members:
        return _error_page(request, tenant_id, 404, "Member Not Found", f"No member record for ID {member_id}.")

    errors, deposit_cents = _validate_sub_account_form(nickname, account_type, opening_deposit)
    if errors:
        return _templates(tenant_id).TemplateResponse(
            request,
            "sub_account_form.html",
            {
                "member_id": member_id,
                "errors": errors,
                "form": {"nickname": nickname, "account_type": account_type, "opening_deposit": opening_deposit},
            },
            status_code=422,
        )

    sub_account_id = next_sub_account_id(tenant)
    from mock_bank_app.data import SubAccount

    sub_account = SubAccount(sub_account_id, member_id, account_type, nickname, deposit_cents)
    tenant.sub_accounts[sub_account_id] = sub_account
    return _templates(tenant_id).TemplateResponse(request, "sub_account_confirmation.html", {"sub_account": sub_account})


@app.get("/")
def root():
    return RedirectResponse(url="/default/members")
