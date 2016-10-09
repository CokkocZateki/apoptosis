import json

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

import itertools

from tornado.httpclient import AsyncHTTPClient, HTTPRequest

from apoptosis.log import app_log, sec_log, svc_log
from apoptosis.helpers import cached

from apoptosis import config


async def slack_request(action, **params):
    slack_client = AsyncHTTPClient()

    params["token"] = config.slack_apitoken
    params = urlencode(params)

    url = "https://slack.com/api/{0}?{1}".format(action, params)

    svc_log.info("requesting {}".format(url))
 
    request = HTTPRequest(url)
    response = await slack_client.fetch(request)

    return json.loads(response.body.decode("utf-8"))


async def group_message(group_slug, message):
    """Send a message to a group."""
    channel_id = await group_slug_to_id(group_slug)
    return await slack_request("chat.postMessage", channel=channel_id, text=message, username="apoptosis", parse="full")


async def group_ping(group_name, message):
    """Send a message to a group prefixed to notify everyone."""
    message = "@everyone " + message
    return await group_message(group_name, message)


async def group_invite(group_slug, user_id):
    """Invite a user to a group."""
    # XXX should use emails
    channel_id = await group_slug_to_id(group_slug)
    return await slack_request("groups.invite", channel=channel_id, user=user_id)


async def group_kick(group_slug, user_id):
    """Kick a member from a group."""
    # XXX should use emails
    channel_id = await group_slug_to_id(group_slug)
    return await slack_request("groups.kick", channel=channel_id, user=user_id)


async def group_create(group_slug):
    """Create a group. Initially we check if the group already exists if it does we
       unarchive the group."""
    channel_id = await group_slug_to_id(group_slug)

    if channel_id:
        svc_log.warn("creation of group {} is causing unarchival".format(group_slug))
        return await group_unarchive(group_slug)
    else:
        svc_log.warn("created group {}".format(group_slug))
        response = await slack_request("groups.create", name=group_slug)
        return response["group"]["id"]

async def group_remove(group_slug):
    """Remove a group by archiving it."""
    # XXX kick all people
    return await group_archive(group_slug)

async def group_members(group_slug):
    slack_id = await group_slug_to_id(group_slug)
    response = await slack_request("groups.info", channel=slack_id)
    return response["group"]["members"]

async def group_upkeep(group_slug, member_emails):
    """See if any members in the group are not allowed to be in this group,
       this function gets called with all allowed members."""
    channel_id = await group_slug_to_id(group_slug)

    wanted = set(user_email_to_id(member_email) for member_email in member_emails)
    current = set(member for member in group_members(group_slug) if member != "U1YTLNYDC")  # XXX

    to_invite = wanted - current
    to_kick = current - wanted

    for member in to_invite:
        await group_invite(group_slug, member)

    for member in to_kick:
        await group_kick(group_slug, member)

    return True

async def group_archive(group_slug):
    """Archive a channel making it unavailable to users."""
    channel_id = await group_slug_to_id(group_slug)

    await slack_request("groups.archive", channel=channel_id)
    svc_log.warn("archived channel {}".format(group_slug))

async def group_unarchive(group_slug):
    """Restore a channel from the archive so it can be re-used."""
    channel_id = await group_slug_to_id(group_slug)

    await slack_request("groups.unarchive", channel=channel_id)
    svc_log.warn("unarchived channel {}".format(group_slug))

#@cached(86400)
async def group_slug_to_id(group_slug):
    groups = await slack_request("groups.list")
    groups = groups["groups"]

    for group in groups:
        if group["name"] == group_slug:
            return group["id"]
    else:
        raise ValueError("No Slack group found")


async def groups_upkeep(group_slugs):
    """Iterate through the group slugs, archiving channels that do not exist in the list and
       creating/unarchiving does that do."""

    slack_groups = await slack_request("groups.list")

    group_slugs = set(["midnight-rodeo"] + group_slugs)
    slack_slugs= [group["name"] for group in slack_groups if not group["is_archived"]]

    to_create = group_slugs - slack_slugs
    to_remove = slack_slugs - group_slugs

    for group in to_create:
        await group_create(group)

    for group in to_remove:
        await group_upkeep(group, [])
        await group_remove(group)

    return True


@cached(86400)
def user_email_to_id(user_email):
    users = slack_request("users.list")["members"]

    for user in users:
        if user["profile"].get("email", None) == user_email:
            return user["id"]


def user_info(user_email):
    user_id = user_email_to_id(user_email)
    return slack_request("users.info", user=user_id)["user"]


def verify(user_email):
    message = "Hello, your authentication code is: {code}. Please paste this back into HK Auth so we can confirm you are the owner of this account,".format(code=identity.verification_code)

    return private_message(user_email, message)

def private_message(user_email, message):
    user_id = user_email_to_id(user_email)
    channel_id = slack_request("im.open", user=user_id)["channel"]["id"]

    return slack_request("chat.postMessage", channel=channel_id, text=message, username="apoptosis", parse="full")

