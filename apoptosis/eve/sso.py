import json

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

import base64

import tornado.httpclient

from apoptosis import config

from apoptosis.models import session

from apoptosis.eve.crest import default_scopes as crest_scopes
from apoptosis.eve.esi import default_scopes as esi_scopes

from anoikis.api.exceptions import InvalidToken, ExpiredToken


default_scopes = set()
default_scopes.update(crest_scopes)
default_scopes.update(esi_scopes)

sso_auth = base64.b64encode("{}:{}".format(config.evesso_clientid, config.evesso_secretkey).encode("utf-8")).decode("ascii")
sso_login = "https://login.eveonline.com/oauth/authorize?" + urlencode({
    "response_type": "code",
    "redirect_uri": config.evesso_callback,
    "client_id": config.evesso_clientid,
    "scope": " ".join(default_scopes),
    "state": "foo"  # XXX make JWT
})


def refresh_access_token(character):
    """Use a characters refresh token to request a new access token."""
    if character.refresh_token is None:
        print("no refresh token for {}".format(character))
        return

    client = tornado.httpclient.HTTPClient()
    request = tornado.httpclient.HTTPRequest(
        "https://login.eveonline.com/oauth/token",
        method="POST",
        headers={
            "Authorization": "Basic {}".format(sso_auth),
            "Content-Type": "application/json",
            "User-Agent": "Hard Knocks Inc. Authentication System"
        },
        body=json.dumps({
            "grant_type": "refresh_token",
            "refresh_token": character.refresh_token
        })
    )

    response = client.fetch(request)
    response = json.loads(response.body.decode("utf-8"))

    print("got new at", response)

    character.access_token = response["access_token"]

    session.add(character)
    session.commit()

    return response["access_token"]
