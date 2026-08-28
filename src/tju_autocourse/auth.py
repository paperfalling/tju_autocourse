"""TJU single-sign-on authentication used by the course system."""

from __future__ import annotations

from urllib.parse import urljoin

import aiohttp
from lxml import etree, html


class AuthenticationError(RuntimeError):
    """Raised when TJU SSO rejects or cannot complete a login."""


def _hidden_fields(body: str) -> dict[str, str]:
    try:
        tree = html.fromstring(body)
    except (ValueError, etree.ParserError):
        return {}
    return {
        str(node.get("name")): str(node.get("value") or "")
        for node in tree.xpath("//input[@name]")
        if node.get("type", "").lower() == "hidden"
    }


async def _response_json(response: aiohttp.ClientResponse) -> dict:
    try:
        value = await response.json(content_type=None)
    except (ValueError, aiohttp.ContentTypeError) as exc:
        raise AuthenticationError("TJU login helper returned invalid data") from exc
    if not isinstance(value, dict):
        raise AuthenticationError("TJU login helper returned invalid data")
    return value


async def login(
    session: aiohttp.ClientSession,
    domain: str,
    username: str,
    password: str,
) -> None:
    """Log in through TJU CAS and leave all issued cookies in ``session``.

    The current TJU CAS flow uses ``lt``/``execution`` plus an RSA value and
    image captcha.  WePeiYang uses the same public ``learning.twt.edu.cn``
    helpers; using them here avoids requiring users to copy browser cookies.
    """

    cas_url = "https://sso.tju.edu.cn/cas/login"
    try:
        async with session.get(cas_url, allow_redirects=False) as response:
            if response.status == 302:
                location = response.headers.get("Location")
                for _ in range(5):
                    if not location:
                        break
                    async with session.get(
                        urljoin(cas_url, location), allow_redirects=False
                    ) as redirected:
                        location = redirected.headers.get("Location")
                        if redirected.status != 302:
                            break
                return
            body = await response.text()
            fields = _hidden_fields(body)
        execution = fields.get("execution")
        lt = fields.get("lt")
        if not execution or not lt:
            raise AuthenticationError("TJU CAS login form is missing execution/lt")

        async with session.post(
            "https://learning.twt.edu.cn/enc",
            data={"val": username + password + lt},
        ) as response:
            encoded = await _response_json(response)
            rsa = encoded.get("data")
        if not rsa:
            raise AuthenticationError("TJU login helper did not return RSA data")

        async with session.get("https://sso.tju.edu.cn/cas/code") as response:
            if response.status >= 400:
                raise AuthenticationError("unable to obtain TJU captcha")
            image = await response.read()
        form = aiohttp.FormData()
        form.add_field(
            "image", image, filename="captcha.jpg", content_type="image/jpeg"
        )
        async with session.post(
            "https://learning.twt.edu.cn/ocr", data=form
        ) as response:
            ocr = await _response_json(response)
            code = ocr.get("data")
        if not code:
            raise AuthenticationError("TJU captcha recognition returned no code")

        payload = {
            "code": str(code),
            "ul": str(len(username)),
            "pl": str(len(password)),
            "lt": lt,
            "rsa": str(rsa),
            "execution": execution,
            "_eventId": "submit",
        }
        async with session.post(
            cas_url, data=payload, allow_redirects=False
        ) as response:
            result = await response.text()
            if response.status != 302 and "remind_strong_pwd = 'true'" not in result:
                raise AuthenticationError("invalid username, password, or captcha")
            location = response.headers.get("Location")

        # CAS redirects to the EAMS host; follow the chain so its session
        # cookie is present before the first course request.
        for _ in range(5):
            if not location:
                break
            next_url = urljoin(cas_url, location)
            async with session.get(next_url, allow_redirects=False) as response:
                location = response.headers.get("Location")
                if response.status != 302:
                    break
    except AuthenticationError:
        raise
    except (aiohttp.ClientError, TimeoutError) as exc:
        raise AuthenticationError("unable to reach TJU login services") from exc
