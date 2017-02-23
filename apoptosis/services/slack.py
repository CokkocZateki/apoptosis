import json

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

import itertools

import tornado.gen

from tornado.httpclient import AsyncHTTPClient, HTTPRequest

from apoptosis.log import app_log, sec_log, svc_log
from apoptosis.helpers import cached

from apoptosis import config

USER_EMAIL_TO_ID = {}


async def slack_request(action, **params):
    slack_client = AsyncHTTPClient()

    params["token"] = config.slack_apitoken

    encoded_params = urlencode(params)

    url = "https://slack.com/api/{0}?{1}".format(action, encoded_params)

    svc_log.info("requesting {}".format(url))
 
    request = HTTPRequest(url)
    try:
        response = await slack_client.fetch(request)
    except tornado.httpclient.HTTPError as e:
        # XXX Wait for throttling
        if e.code == 429:
            retry_after = e.response.headers.get("Retry-After", None)

            if retry_after is not None:
                svc_log.warn("slack throttled for {}s".format(retry_after))

                await tornado.gen.sleep(int(retry_after) + 1)

                # Redo our call
                response = await slack_client.fetch(request)
        else:
            raise

    return json.loads(response.body.decode("utf-8"))


async def group_message(group_slug, message):
    """Send a message to a group."""
    channel_id = await group_slug_to_id(group_slug)
    return await slack_request("chat.postMessage", channel=channel_id, text=message, username="apoptosis", parse="full")


async def group_ping(group_name, message):
    """Send a message to a group prefixed to notify everyone."""
    message = "@channel " + message
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
    return set(response["group"]["members"])

async def group_upkeep(group):
    """See if any members in the group are not allowed to be in this group,
       this function gets called with all allowed members."""

    slack_channel_id = await group_slug_to_id(group.slug)

    slack_channel_current_members = await group_members(group.slug)
    slack_channel_current_members = set(member for member in slack_channel_current_members if member != 'U1YTLNYDC')
    slack_channel_wanted_members = set()

    # Get all members in this group, look up their slack ID (if any)
    for member in group.members:
        for identity in member.slack_identities:
            slack_member = await user_email_to_id(identity.email)
            if slack_member:
                slack_channel_wanted_members.add(slack_member)

    slack_to_invite = slack_channel_wanted_members - slack_channel_current_members
    slack_to_kick = slack_channel_current_members - slack_channel_wanted_members

    svc_log.warn("running slack group upkeep for {} ({}), inviting {}, kicking {}".format(group.slug, len(slack_channel_current_members), len(slack_to_invite), len(slack_to_kick)))

    if group.slug not in ('eft-warriors', 'atxv', 'tech', 'specops', 'intel-hk', 'intel-citadels', 'intel-capitals', 'intel-supers', 'roamers'):
        print("yes")
        return

    for member in slack_to_invite:
        await group_invite(group.slug, member)

    for member in slack_to_kick:
        await group_kick(group.slug, member)

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

async def group_slug_to_id(group_slug):
    groups = await slack_request("groups.list")
    groups = groups["groups"]

    for group in groups:
        if group["name"] == group_slug:
            return group["id"]
    else:
        raise ValueError("No Slack group found for", group_slug)

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

async def user_id_to_email(user_id):
    users = await slack_request("users.list")
    users = users["members"]

    for user in users:
        if user["profile"].get("id", None) == user_id:
            return user["email"]


async def user_email_to_id(user_email):
    if user_email in USER_EMAIL_TO_ID:
        return USER_EMAIL_TO_ID[user_email]

    users = await slack_request("users.list")
    users = users["members"]

    for user in users:
        if user["profile"].get("email", None) == user_email:
            USER_EMAIL_TO_ID[user_email] = user["id"]
            return user["id"]


async def refresh_user_email_to_ids():
    users = await slack_request("users.list")
    users = users["members"]

    for user in users:
        user_email = user["profile"].get("email", None)

        if user_email is not None:
            USER_EMAIL_TO_ID[user_email] = user["id"]


def user_info(user_email):
    user_id = user_email_to_id(user_email)
    return slack_request("users.info", user=user_id)["user"]


async def verify(slackidentity):
    message = "Hello, your authentication code is: {code}. Please paste this back into HK Auth so we can confirm you are the owner of this account,".format(code=slackidentity.verification_code)
    return await private_message(slackidentity.email, message)

async def private_message(user_email, message):
    user_id = await user_email_to_id(user_email)

    channel_id = await slack_request("im.open", user=user_id)
    try:
        channel_id = channel_id["channel"]["id"]
    except:
        return False

    return await slack_request("chat.postMessage", channel=channel_id, text=message, username="apoptosis", parse="full")
