from tornado.httpclient import HTTPClient, HTTPError

from lxml import etree

from hkauth.exceptions import (
    InvalidAPIKey
)

from hkauth.helpers import cached

@cached(time=1800)
def character(character_id):
    http_client = HTTPClient()

    try:
        response = http_client.fetch("https://api.eveonline.com/eve/CharacterInfo.xml.aspx?characterID={}".format(character_id))
    except HTTPError as e:
        if e.code in (400, 403):
            raise InvalidAPIKey()
        else:
            raise

    document = etree.fromstring(response.body)

    http_client.close()

    result = document.xpath("/eveapi/result")[0]

    # Special cases that might not exist in the result
    alliance_id = None
    alliance_name = None

    if len(result.xpath("allianceID")):
        alliance_id = int(result.xpath("allianceID")[0].text)

    if len(result.xpath("alliance")):
        alliance_name = result.xpath("alliance")[0].text

    return {
        "character_id": int(result.xpath("characterID")[0].text),
        "character_name": result.xpath("characterName")[0].text,
        "corporation_id": int(result.xpath("corporationID")[0].text),
        "corporation_name": result.xpath("corporation")[0].text,
        "alliance_id": alliance_id,
        "alliance_name": alliance_name
    }
