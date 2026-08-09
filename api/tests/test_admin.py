from tests.util import FRIEND, LORDO, do_login


async def test_member_cannot_read_audit(claimed, client, fake_idp):
    await do_login(client, fake_idp, FRIEND)
    resp = await client.get("/api/admin/audit")
    assert resp.status_code == 403


async def test_admin_reads_audit_with_filter(client, fake_idp):
    await do_login(client, fake_idp, LORDO)

    resp = await client.get("/api/admin/audit")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert any(r["action"] == "auth.login" for r in body["rows"])

    filtered = await client.get("/api/admin/audit", params={"action": "auth.login"})
    assert all(r["action"] == "auth.login" for r in filtered.json()["rows"])


async def test_audit_requires_auth(client):
    resp = await client.get("/api/admin/audit")
    assert resp.status_code == 401
