"""SchoolGridApi against a fake SchoolGrid site (ASP.NET-style form login + cookie-protected JSON API)."""
import aiohttp
import pytest
from aiohttp import web

from custom_components.schoolgrid import api as api_mod
from custom_components.schoolgrid.api import AuthError, SchoolGridApi


LOGIN_HTML = '<form><input type="hidden" name="__VIEWSTATE" value="vs"/><input type="hidden" name="__EVENTVALIDATION" value="ev"/></form>'
U, P = "ctl00$ctl00$bodyContent$bodyContent$username", "ctl00$ctl00$bodyContent$bodyContent$password"


@pytest.fixture
async def site(socket_enabled):
    state = {"valid": set(), "logins": 0, "last_form": None}

    async def login(req):
        if req.method == "GET":
            return web.Response(text=LOGIN_HTML, content_type="text/html")
        form = dict(await req.post())
        state["last_form"] = form
        if form.get(U) == "me@x.com" and form.get(P) == "secret" and form.get("__VIEWSTATE") == "vs":
            state["logins"] += 1
            tok = f"t{state['logins']}"
            state["valid"].add(tok)
            r = web.Response(status=302, headers={"Location": "/"})
            r.set_cookie("auth", tok, httponly=True)
            return r
        return web.Response(text=LOGIN_HTML, content_type="text/html")

    async def data(req):
        if req.cookies.get("auth") in state["valid"]:
            return web.json_response({"ok": True, "method": req.method})
        return web.Response(status=302, headers={"Location": "/login.aspx?ReturnUrl=%2F"})

    app = web.Application()
    app.router.add_route("*", "/login.aspx", login)
    app.router.add_route("*", "/api/{tail:.*}", data)
    runner = web.AppRunner(app)
    await runner.setup()
    site_ = web.TCPSite(runner, "127.0.0.1", 0)
    await site_.start()
    port = site_._server.sockets[0].getsockname()[1]
    old = api_mod.BASE_URL
    api_mod.BASE_URL = f"http://127.0.0.1:{port}"
    state["url"] = api_mod.BASE_URL
    yield state
    api_mod.BASE_URL = old
    await runner.cleanup()


async def make(user="me@x.com", pw="secret"):
    session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True))
    return session, SchoolGridApi(session, user, pw)


async def test_logs_in_lazily_and_reuses_session(site):
    session, api = await make()
    assert (await api.accounts())["ok"]
    assert (await api.accounts())["ok"]
    assert site["logins"] == 1
    assert site["last_form"][U] == "me@x.com"
    await session.close()


async def test_relogs_in_after_expiry_including_posts(site):
    session, api = await make()
    await api.accounts()
    site["valid"].clear()
    assert (await api.insert_order({"a": 1}))["method"] == "POST"
    assert site["logins"] == 2
    await session.close()


async def test_bad_password_raises_auth_error(site):
    session, api = await make(pw="wrong")
    with pytest.raises(AuthError):
        await api.accounts()
    await session.close()
