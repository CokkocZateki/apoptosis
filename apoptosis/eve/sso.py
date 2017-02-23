import json

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

import base64

import tornado.httpclient

from apoptosis import config

from apoptosis.models import session
from apoptosis.log import app_log
from apoptosis.eve.esi import default_scopes as esi_scopes

from anoikis.api.exceptions import InvalidToken, ExpiredToken


default_scopes = set()
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
        app_log.warn("no refresh token for {}".format(character))
        return

    app_log.debug("refreshing access token for {}".format(character.character_name))

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

    try:
        response = client.fetch(request)
        response = json.loads(response.body.decode("utf-8"))

        character.access_token = response["access_token"]

        session.add(character)
        session.commit()

        app_log.debug("got new access token for {}".format(character))
    except tornado.httpclient.HTTPError:
        app_log.info("failed retrieving new access token for {}".format(character))

        character.access_token = None
        character.refresh_token = None

        session.add(character)
        session.commit()

        raise Exception("")  # XXX proper type
