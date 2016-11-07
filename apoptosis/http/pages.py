import json

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

import base64

from datetime import datetime

import tornado.web
import tornado.httpclient

from apoptosis.log import app_log, sec_log
from apoptosis.services import slack
from apoptosis.cache import redis_cache
from apoptosis import config
from apoptosis.eve.crest import default_scopes

from apoptosis.http.base import (
    AuthPage
)


from apoptosis.models import session
from apoptosis.models import (
    UserModel,
    UserLoginModel,
    CharacterModel,
    SlackIdentityModel,
    GroupModel,
    MembershipModel
)

import apoptosis.cron.user as cron_user



sso_auth = base64.b64encode("{}:{}".format(config.evesso_clientid, config.evesso_secretkey).encode("utf-8")).decode("ascii")
sso_login = "https://login.eveonline.com/oauth/authorize?" + urlencode({
    "response_type": "code",
    "redirect_uri": config.evesso_callback,
    "client_id": config.evesso_clientid,
    "scope": " ".join(default_scopes),
    "state": "foo"  # XXX make JWT
})


def login_required(func):
    async def inner(self, *args, **kwargs):
        self.requires_login()
        await func(self)
    return inner

def internal_required(func):
    async def inner(self, *args, **kwargs):
        self.requires_internal()
        await func(self)
    return inner

def admin_required(func):
    async def inner(self, *args, **kwargs):
        self.requires_admin()
        await func(self)
    return inner


class LoginPage(AuthPage):
    async def get(self):
        if self.current_user:
            return self.redirect("/")
        else:
            return self.render("login.html", login_url=sso_login)


class LoginCallbackPage(AuthPage):
    async def get(self):
        # XXX do this depending on the code

        # This callback can go two ways depending on the fact if someone
        # is already logged in. If they are we are adding a character to
        # their account. If they are not we are either logging them in
        # or creating their account.
        code = self.get_argument("code", None)
        state = self.get_argument("state", None)

        if not code or not state:
            return  # XXX

        # XXX clean code!?
        # XXX check state!?

        if self.current_user:
            return await self._add()
        else:
            return await self._login()

    async def _sso_response(self):
        code = self.get_argument("code", None)
        state = self.get_argument("state", None)

        if not code or not state:
            return  # XXX veryfy code and state

        sso_client = tornado.httpclient.AsyncHTTPClient()
        request = tornado.httpclient.HTTPRequest(
            "https://login.eveonline.com/oauth/token",
            method="POST",
            headers={
                "Authorization": "Basic {}".format(sso_auth),
                "Content-Type": "application/json"
            },
            body=json.dumps({
                "grant_type": "authorization_code",
                "code": code
            })
        )

        response = await sso_client.fetch(request)
        response = json.loads(response.body.decode("utf-8"))

        access_token = response["access_token"]
        refresh_token = response["refresh_token"]

        request = tornado.httpclient.HTTPRequest(
            "https://login.eveonline.com/oauth/verify",
            headers={
                "Authorization": "Bearer {}".format(access_token),
                "User-Agent": "Hard Knocks Inc. Authentication System"
            }
        )

        response = await sso_client.fetch(request)
        response = json.loads(response.body.decode("utf-8"))

        character_id = response["CharacterID"]
        character_scopes = response["Scopes"].split(" ")

        account_hash = response["CharacterOwnerHash"]

        return character_id, character_scopes, access_token, refresh_token, account_hash

    async def _create(self, character_id, character_scopes, access_token, refresh_token, account_hash): 
        # We don't have an account with this character on it yet. Let's fetch the 
        # character information from the XML API and fill it into a model, tie it
        # up to a fresh new user and log it in
        character = await CharacterModel.from_xml_api(character_id)
        character.access_token = access_token
        character.refresh_token = refresh_token
        character.account_hash = account_hash

        # For our scopes we see if they already exist, if they don't we create them and hang them
        # on the character
        character.update_scopes(character_scopes)

        return character

    async def _add(self):
        character_id, character_scopes, access_token, refresh_token, account_hash = await self._sso_response()

        # See if we already have this character
        character = session.query(CharacterModel).filter(CharacterModel.character_id==character_id).first()

        if character: # XXX add new scopes
            if character.user == self.current_user:
                # update scopes
                a = 1
            else:
                sec_log.warn("user {} tried to add {} but belongs to {}".format(self.current_user, character, character.user))
                raise tornado.web.HTTPError(403)
        else:
            character = await self._create(character_id, character_scopes, access_token, refresh_token, account_hash)

        # Append the character to the currently logged in character
        self.current_user.characters.append(character)
        self.current_user.chg_date = datetime.now()

        session.add(self.current_user)
        session.commit()

        sec_log.info("added %s for %s" % (character, character.user))

        cron_user.setup_character(character)

        self.redirect("/characters/add/success")

    async def _login(self):
        character_id, character_scopes, access_token, refresh_token, account_hash = await self._sso_response()

        # See if we already have this character
        character = session.query(CharacterModel).filter(CharacterModel.character_id==character_id).first()

        # The character already exists so we log in to the corresponding user and
        # redirect to the success page
        if character:
            if character.account_hash != account_hash:
                sec_log.critical("account hash for %s changed denying login" % character)
                raise tornado.web.HTTPError(400)

            sec_log.info("logged in %s through %s" % (character.user, character))
            self.set_current_user(character.user)

            login = UserLoginModel()
            login.user = character.user
            login.pub_date = datetime.now()
            login.ip_address = self.request.remote_ip

            session.add(login)
            session.commit()

            return self.redirect("/login/success")
        else:
            # We don't have an account with this character on it yet. Let's fetch the 
            # character information from the XML API and fill it into a model, tie it
            # up to a fresh new user and log it in
            character = await self._create(character_id, character_scopes, access_token, refresh_token, account_hash)
            character.is_main = True
            character.pub_date = datetime.now()

            user = UserModel()
            user.characters.append(character)
            user.pub_date = datetime.now()
            user.chg_date = datetime.now()

            session.add(user)
            session.commit()

            self.set_current_user(user)

            sec_log.info("created %s through %s" % (character.user, character))

            login = UserLoginModel()
            login.user = character.user
            login.pub_date = datetime.now()
            login.ip_address = self.request.remote_ip

            session.add(login)
            session.commit()

            cron_user.setup_character(character)

            # Redirect to another page with some more information for the user of what
            # is going on
            return self.redirect("/login/created")


class LoginSuccessPage(AuthPage):

    @login_required
    async def get(self):
        return self.render("login_success.html")


class LoginCreatedPage(AuthPage):

    @login_required
    async def get(self):
        return self.render("login_created.html")

class LogoutPage(AuthPage):

    @login_required
    async def post(self):
        self.set_current_user(None)

        return self.redirect("/logout/success")

class LogoutSuccessPage(AuthPage):
    async def get(self):
        return self.render("logout_success.html")


class HomePage(AuthPage):
    async def get(self):
        return self.render("home.html")


class CharactersPage(AuthPage):

    @login_required
    async def get(self):
        return self.render("characters.html", login_url=sso_login)


class CharactersSelectMainPage(AuthPage):

    @login_required
    async def post(self):
        character = self.model_by_id(CharacterModel, "character_id")

        for char in self.current_user.characters:
            char.is_main = False

        character.is_main = True
        
        session.add(self.current_user)
        session.commit()

        # TRIGGER LDAP

        return self.redirect("/characters/select_main/success")


class CharactersSelectMainSuccessPage(AuthPage):

    @login_required
    async def get(self):
        return self.render("characters_select_main_success.html")


class ServicesPage(AuthPage):

    @login_required
    async def get(self):
        return self.render("services.html")


class ServicesAddSlackIdentityPage(AuthPage):

    @login_required
    async def post(self):
        slack_id = self.get_argument("slack_id", None)

        if not slack_id:
            raise tornado.web.HTTPError(400)

        slackidentity = SlackIdentityModel(slack_id)
        slackidentity.user = self.current_user

        session.add(slackidentity)
        session.commit()

        sec_log.info("slackidentity {} added to {}".format(slackidentity, slackidentity.user))

        return self.redirect("/services/add_slack_identity/success?slackidentity_id={id}".format(id=slackidentity.id))


class ServicesAddSlackIdentitySuccessPage(AuthPage):

    @login_required
    async def get(self):
        slackidentity = self.model_by_id(SlackIdentityModel, "slackidentity_id")

        return self.render("services_add_slack_identity_success.html", slackidentity=slackidentity)


class ServicesSendVerificationSlackIdentityPage(AuthPage):

    @login_required
    async def post(self):
        slackidentity = self.model_by_id(SlackIdentityModel, "slackidentity_id")

        slack.send_verification(slackidentity.email)

        sec_log.info("slackidentity {} for {} sent verification".format(slackidentity, slackidentity.user))

        return self.render("services_verify_slack_identity.html", slackidentity=slackidentity)


class ServicesVerifyVerificationSlackIdentityPage(AuthPage):

    @login_required
    async def post(self):
        code = self.get_argument("code", None)

        slackidentity = self.model_by_id(SlackIdentityModel, "slackidentity_id")

        if slackidentity.verification_code == code:
            slackidentity.verification_done = True

            session.add(slackidentity)
            session.commit()

            sec_log.info("slackidentity {} for {} verified".format(slackidentity, slackidentity.user))

            return self.redirect("/services/verify_slack_verification/success?slackidentity_id={}".format(slackidentity.id))
        else:
            return self.redirect("/services/verify_slack_verification/failure?slackidentity_id={}".format(slackidentity.id))


class ServicesVerifySlackIdentitySuccessPage(AuthPage):

    @login_required
    async def get(self):
        slackidentity = self.model_by_id(SlackIdentityModel, "slackidentity_id")

        return self.render("services_verify_slack_identity_success.html", slackidentity=slackidentity)


class GroupsPage(AuthPage):

    @login_required
    @internal_required
    async def get(self):
        groups = session.query(GroupModel).all()

        return self.render("groups.html", groups=groups)


class GroupsJoinPage(AuthPage):

    @login_required
    @internal_required
    async def post(self):
        group = self.model_by_id(GroupModel, "group_id")

        membership = MembershipModel()
        membership.user = self.current_user
        membership.group = group

        if group.requires_approval:
            membership.pending = True

        session.add(membership)
        session.commit()

        sec_log.info("user {} joined group {}".format(membership.user, membership.group))

        # XXX Update the entire group
        slack.group_upkeep(group.slug, [member.slack_identities[0].email for member in group.members if len(member.slack_identities)])

        return self.redirect("/groups/join/success?membership_id={}".format(membership.id))


class GroupsJoinSuccessPage(AuthPage):

    @login_required
    @internal_required
    async def get(self):
        membership = self.model_by_id(MembershipModel, "membership_id")

        return self.render("groups_join_success.html", membership=membership)


class GroupsLeavePage(AuthPage):

    @login_required
    @internal_required
    async def post(self):
        group = self.model_by_id(GroupModel, "group_id")

        for membership in group.memberships:
            if membership.user == self.current_user:
                session.delete(membership)
                session.commit()

                break
        else:
            raise tornado.web.HTTPError(400)

        sec_log.info("user {} left group {}".format(membership.user, membership.group))

        slack.group_upkeep(group.slug, [member.slack_identities[0].email for member in group.members if len(member.slack_identities)])

        return self.redirect("/groups/leave/success?group_id={}".format(group.id))


class GroupsLeaveSuccessPage(AuthPage):

    @login_required
    @internal_required
    async def get(self):
        group = self.model_by_id(GroupModel, "group_id")

        return self.render("groups_leave_success.html", group=group)


class PingPage(AuthPage):

    @login_required
    @internal_required
    async def get(self):
        return self.render("ping.html")


class PingSendAllPage(AuthPage):

    @login_required
    @internal_required
    async def post(self):
        message = self.get_argument("message", None)

        if not message:
            raise tornado.web.HTTPError(400)

        message = "{} ({})".format(message, self.current_user.main_character.character_name)

        result = await slack.group_ping("midnight-rodeo", message)

        app_log.info(
            "%s sent all ping: %s" % (self.current_user, message)
        )

        return self.redirect("/ping/send_all/success")


class PingSendAllSuccessPage(AuthPage):

    @login_required
    @internal_required
    async def get(self):
        return self.render("ping_all_success.html")


class PingSendGroupPage(AuthPage):

    @login_required
    @internal_required
    async def post(self):
        message = self.get_argument("message", None)
        group = self.model_by_id(GroupModel, "group_id")

        if not message:
            raise tornado.web.HTTPError(400)

        message = "{} ({})".format(message, self.current_user.main_character.character_name)

        result = await slack.group_ping(group.slug, message)

        app_log.info(
            "%s sent group ping to %s: %s" % (self.current_user, group, message)
        )

        return self.redirect("/ping/send_group/success?group_id={}".format(group.id))


class PingSendGroupSuccessPage(AuthPage):

    @login_required
    @internal_required
    async def get(self):
        group = self.model_by_id(GroupModel, "group_id")

        return self.render("ping_group_success.html", group=group)


class AdminPage(AuthPage):

    @login_required
    @internal_required
    @admin_required
    async def get(self):
        characters = [character for character in session.query(CharacterModel).all()]

        glance_total = len(characters)
        glance_online = len([character for character in characters if character.is_online])
        glance_internal = len([character for character in characters if character.is_internal])

        return self.render(
            "admin.html",
            glance_total=glance_total,
            glance_online=glance_online,
            glance_internal=glance_internal
        )

class AdminGroupsPage(AuthPage):

    @login_required
    @internal_required
    @admin_required
    async def get(self):
        groups = session.query(GroupModel).all()

        return self.render("admin_groups.html", groups=groups)


class AdminGroupsCreatePage(AuthPage):

    @login_required
    @internal_required
    @admin_required
    async def get(self):
        return self.render("admin_groups_create.html")


class AdminUsersPage(AuthPage):

    @login_required
    @internal_required
    @admin_required
    async def get(self):
        users = session.query(UserModel).all()

        return self.render("admin_users.html", users=users)


class AdminCharactersPage(AuthPage):

    @login_required
    @internal_required
    @admin_required
    async def get(self):
        characters = session.query(CharacterModel).all()

        return self.render("admin_characters.html", characters=characters)

class AdminGroupsPage(AuthPage):

    @login_required
    @internal_required
    @admin_required
    async def get(self):
        groups = session.query(GroupModel).all()

        return self.render("admin_groups.html", groups=groups)
