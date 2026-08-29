"""TJU single-sign-on authentication used by the course system."""

from __future__ import annotations

from urllib.error import URLError
from urllib.parse import urljoin, urlparse

import lxml.etree
from lxml import html

from .eams import AuthenticationError, SyncSession


def _hidden_fields(body: str) -> dict[str, str]:
    try:
        tree = html.fromstring(body)
    except (ValueError, lxml.etree.ParserError):
        return {}
    return {
        str(node.get("name")): str(node.get("value") or "")
        for node in tree.xpath("//input[@name]")
        if node.get("type", "").lower() == "hidden"
    }


def _response_json(response) -> dict:
    try:
        import json

        value = json.loads(response.text)
    except (ValueError, TypeError) as exc:
        raise AuthenticationError("TJU login helper returned invalid data") from exc
    if not isinstance(value, dict):
        raise AuthenticationError("TJU login helper returned invalid data")
    return value


def _follow_redirects(
    session: SyncSession,
    base_url: str,
    location: str | None,
) -> None:
    if not location:
        raise AuthenticationError("TJU login redirect is missing Location")
    for _ in range(5):
        next_url = urljoin(base_url, location)
        response = session.get(next_url)
        if 300 <= response.status < 400:
            location = response.headers.get("Location")
            if not location:
                raise AuthenticationError("TJU login redirect is missing Location")
            base_url = next_url
            continue
        if not 200 <= response.status < 300:
            host = urlparse(next_url).netloc or "unknown"
            raise AuthenticationError(
                f"TJU login redirect failed (status={response.status}, host={host})"
            )
        return
    raise AuthenticationError("TJU login redirect chain is too long")


def login(
    session: SyncSession,
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
    service_url = f"https://{domain}/eams/stdElectCourse!defaultPage.action"
    service_params = {"service": service_url}
    try:
        response = session.get(cas_url, params=service_params)
        if 300 <= response.status < 400:
            _follow_redirects(session, cas_url, response.headers.get("Location"))
            return
        body = response.text
        fields = _hidden_fields(body)
        execution = fields.get("execution")
        lt = fields.get("lt")
        if not execution or not lt:
            raise AuthenticationError("TJU CAS login form is missing execution/lt")

        response = session.post(
            "https://learning.twt.edu.cn/enc",
            data={"val": username + password + lt},
        )
        encoded = _response_json(response)
        rsa = encoded.get("data")
        if not rsa:
            raise AuthenticationError("TJU login helper did not return RSA data")

        response = session.get("https://sso.tju.edu.cn/cas/code")
        if response.status >= 400:
            raise AuthenticationError("unable to obtain TJU captcha")
        image = response.body
        boundary = "----TJUAutoCourseCaptcha"
        multipart = (
            (
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="image"; filename="captcha.jpg"\r\n'
                "Content-Type: image/jpeg\r\n\r\n"
            ).encode()
            + image
            + f"\r\n--{boundary}--\r\n".encode()
        )
        response = session.post(
            "https://learning.twt.edu.cn/ocr",
            data=multipart,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        ocr = _response_json(response)
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
        response = session.post(cas_url, params=service_params, data=payload)
        result = response.text
        if (
            not 300 <= response.status < 400
            and "remind_strong_pwd = 'true'" not in result
        ):
            raise AuthenticationError("invalid username, password, or captcha")
        location = response.headers.get("Location")

        # CAS redirects to the EAMS host; follow the chain so its session
        # cookie is present before the first course request.
        if location:
            _follow_redirects(session, cas_url, location)
    except AuthenticationError:
        raise
    except (URLError, TimeoutError, OSError) as exc:
        raise AuthenticationError("unable to reach TJU login services") from exc
