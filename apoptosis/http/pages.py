import json

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

from datetime import datetime

import tornado.web
import tornado.httpclient

from anoikis.fit.eft import parse as parse_fit
from anoikis.static.skills import skills_item

from apoptosis.log import app_log, sec_log
from apoptosis.services import slack
from apoptosis.eve.sso import sso_auth, sso_login

from apoptosis.http.base import (
    AuthPage
)


from apoptosis.models import (
    session,
    UserModel,
    UserLoginModel,
    CharacterModel,
    SlackIdentityModel,
    GroupModel,
    MembershipModel,
    EVESolarSystemModel
)

import apoptosis.queue.user as queue_user 


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


def special_required(func):
    async def inner(self, *args, **kwargs):
        self.requires_special()
        await func(self)
    return inner


def fc_required(func):
    async def inner(self, *args, **kwargs):
        self.requires_fc()
        await func(self)
    return inner


def hr_required(func):
    async def inner(self, *args, **kwargs):
        self.requires_hr()
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
        # We don't have an account with this character on it yet. Let's fetch
        # the character information from the XML API and fill it into a model,
        # tie it up to a fresh new user and log it in
        character = await CharacterModel.from_api(character_id)
        character.access_token = access_token
        character.refresh_token = refresh_token
        character.account_hash = account_hash

        # For our scopes we see if they already exist, if they don't we create
        # them and hang them on the character
        character.update_scopes(character_scopes)

        return character

    async def _add(self):
        character_id, character_scopes, access_token, refresh_token, account_hash = await self._sso_response()

        # See if we already have this character
        character = session.query(
            CharacterModel).filter(
                CharacterModel.character_id == character_id).first()

        if character:  # XXX add new scopes
            if character.user == self.current_user:
                character.access_token = access_token
                character.refresh_token = refresh_token
                character.account_hash = account_hash

                # For our scopes we see if they already exist, if they
                # don't we create them and hang them on the character
                character.update_scopes(character_scopes)
            else:
                sec_log.warn(
                    "user {} tried to add {} but belongs to {}".format(
                        self.current_user, character, character.user))
                raise tornado.web.HTTPError(403)
        else:
            character = await self._create(
                character_id,
                character_scopes,
                access_token,
                refresh_token,
                account_hash
            )

        # Append the character to the currently logged in character
        self.current_user.characters.append(character)
        self.current_user.chg_date = datetime.now()

        session.add(self.current_user)
        session.commit()

        sec_log.info("added %s for %s" % (character, character.user))

        queue_user.setup_character(character)

        self.flash_success(
            self.locale.translate("CHARACTER_ADD_SUCCESS_ALERT"))

        self.redirect("/characters")

    async def _login(self):
        character_id, character_scopes, access_token, refresh_token, account_hash = await self._sso_response()

        # See if we already have this character
        character = session.query(
            CharacterModel).filter(
                CharacterModel.character_id == character_id).first()

        # The character already exists so we log in to the corresponding user
        # and redirect to the success page
        if character:
            if character.account_hash != account_hash:
                sec_log.critical(
                    "account hash for {} changed denying login".format(
                        character))
                raise tornado.web.HTTPError(400)

            sec_log.info(
                "logged in {} through {}".format(character.user, character))
            self.set_current_user(character.user)

            login = UserLoginModel()
            login.user = character.user
            login.pub_date = datetime.now()
            login.ip_address = self.request.remote_ip

            session.add(login)
            session.commit()

            return self.redirect("/login/success")
        else:
            # We don't have an account with this character on it yet. Let's
            # fetch the character information from the XML API and fill it
            # into a model, tie it up to a fresh new user and log it in
            character = await self._create(
                character_id,
                character_scopes,
                access_token,
                refresh_token,
                account_hash
            )
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

            queue_user.setup_character(character)

            # Redirect to another page with some more information for the
            # user of what is going on
            return self.redirect("/login/created")


class LoginSuccessPage(AuthPage):
    @login_required
    async def get(self):
        self.flash_success(self.locale.translate("LOGIN_SUCCESS_ALERT"))
        return self.redirect("/")


class LoginCreatedPage(AuthPage):
    @login_required
    async def get(self):
        self.flash_success(self.locale.translate("LOGIN_CREATED_ALERT"))
        return self.redirect("/")


class LogoutPage(AuthPage):
    @login_required
    async def post(self):
        self.clear_cookie("user_id")
        return self.redirect("/logout/success")


class LogoutSuccessPage(AuthPage):
    async def get(self):
        self.flash_success(self.locale.translate("LOGOUT_SUCCESS_ALERT"))
        return self.redirect("/")


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

        return self.redirect("/characters/select_main/success")


class CharactersSelectMainSuccessPage(AuthPage):
    @login_required
    async def get(self):
        self.flash_success(
            self.locale.translate("CHARACTERS_CHARACTERS_MAIN_SELECT_SUCCESS"))
        return self.redirect("/characters")


class ServicesPage(AuthPage):
    @login_required
    async def get(self):
        return self.render("services.html")


class ServicesDeleteSlackIdentityPage(AuthPage):
    @login_required
    async def post(self):
        slackidentity = self.model_by_id(
            SlackIdentityModel, "slackidentity_id")

        session.delete(slackidentity)
        session.commit()

        self.flash_success(
            self.locale.translate(
                "SERVICES_DELETE_SLACK_IDENTITY_SUCCESS_ALERT")
        )

        return self.redirect("/services")


class ServicesAddSlackIdentityPage(AuthPage):
    @login_required
    async def post(self):
        slack_id = self.get_argument("slack_id", None)

        if not slack_id:
            raise tornado.web.HTTPError(400)

        slackidentity = SlackIdentityModel(slack_id.lower())
        slackidentity.user = self.current_user

        session.add(slackidentity)
        session.commit()

        sec_log.info(
            "slackidentity {} added to {}".format(
                slackidentity, slackidentity.user)
        )

        return self.redirect(
            "/services/add_slack_identity/success?slackidentity_id={id}".format(
                 id=slackidentity.id)
        )


class ServicesAddSlackIdentitySuccessPage(AuthPage):
    @login_required
    async def get(self):
        self.flash_success(
            self.locale.translate("SERVICES_ADD_SLACK_IDENTITY_SUCCESS_ALERT"))
        return self.redirect("/services")


class ServicesSendVerificationSlackIdentityPage(AuthPage):
    @login_required
    async def post(self):
        slackidentity = self.model_by_id(
            SlackIdentityModel, "slackidentity_id")

        value = await slack.verify(slackidentity)

        if value is False:
            self.flash_error(
                self.locale.translate(
                    "SERVICES_SEND_SLACK_IDENTITY_FAILURE_ALERT"))
            return self.redirect(
                "/services?slackidentity_id={}".format(slackidentity.id))

        sec_log.info(
            "slackidentity {} for {} sent verification".format(
                slackidentity, slackidentity.user)
        )

        return self.render(
            "services_verify_slack_identity.html", slackidentity=slackidentity)


class ServicesVerifyVerificationSlackIdentityPage(AuthPage):
    @login_required
    async def post(self):
        code = self.get_argument("code", None)

        slackidentity = self.model_by_id(
            SlackIdentityModel, "slackidentity_id")

        if slackidentity.verification_code == code:
            slackidentity.verification_done = True

            session.add(slackidentity)
            session.commit()

            sec_log.info(
                "slackidentity {} for {} verified".format(
                    slackidentity, slackidentity.user))
            self.flash_success(
                self.locale.translate(
                    "SERVICES_VERIFY_SLACK_IDENTITY_SUCCESS_ALERT"))

            return self.redirect(
                "/services?slackidentity_id={}".format(slackidentity.id))
        else:
            self.flash_error(
                self.locale.translate(
                    "SERVICES_VERIFY_SLACK_IDENTITY_FAILURE_ALERT"))
            return self.redirect(
                "/services?slackidentity_id={}".format(slackidentity.id))


class ServicesVerifySlackIdentitySuccessPage(AuthPage):
    @login_required
    async def get(self):
        self.flash_success(
            self.locale.translate(
                "SERVICES_VERIFY_SLACK_IDENTITY_SUCCESS_ALERT"))
        return self.redirect("/services")


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
            await slack.group_message(
                group.slug,
                "New pending member: {}".format(
                    self.current_user.main_character.character_name)
            )
            membership.pending = True
        else:
            for identity in self.current_user.slack_identities:
                member = await slack.user_email_to_id(identity.email)
                await slack.group_invite(group.slug, member)

            await slack.group_message(
                group.slug,
                "New member: {}".format(
                    self.current_user.main_character.character_name)
            )

        session.add(membership)
        session.commit()

        sec_log.info(
            "user {} joined group {}".format(
                membership.user, membership.group)
        )

        return self.redirect(
            "/groups/join/success?membership_id={}".format(membership.id))


class GroupsJoinSuccessPage(AuthPage):
    @login_required
    @internal_required
    async def get(self):
        membership = self.model_by_id(MembershipModel, "membership_id")
        if membership.pending:
            self.flash_success(
                self.locale.translate("GROUPS_JOIN_SUCCESS_PENDING_ALERT"))
        else:
            self.flash_success(
                self.locale.translate("GROUPS_JOIN_SUCCESS_DONE_ALERT"))
        return self.redirect("/groups")


class GroupsLeavePage(AuthPage):
    @login_required
    @internal_required
    async def post(self):
        group = self.model_by_id(GroupModel, "group_id")

        for membership in group.memberships:
            if membership.user == self.current_user:
                session.delete(membership)
                session.commit()

                for identity in self.current_user.slack_identities:
                    member = await slack.user_email_to_id(identity.email)
                    await slack.group_kick(group.slug, member)

                await slack.group_message(
                    group.slug,
                    "Member left: {}".format(
                        self.current_user.main_character.character_name)
                )

                break
        else:
            raise tornado.web.HTTPError(400)

        sec_log.info(
            "user {} left group {}".format(membership.user, membership.group))

        return self.redirect(
            "/groups/leave/success?group_id={}".format(group.id))


class GroupsLeaveSuccessPage(AuthPage):
    @login_required
    @internal_required
    async def get(self):
        self.flash_success(self.locale.translate("GROUPS_LEAVE_SUCCESS_ALERT"))
        return self.redirect("/groups")


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

        message = "{} ({})".format(
            message, self.current_user.main_character.character_name)

        await slack.group_ping("midnight-rodeo", message)

        app_log.info(
            "%s sent all ping: %s" % (self.current_user, message)
        )

        return self.redirect("/ping/send_all/success")


class PingSendAllSuccessPage(AuthPage):
    @login_required
    @internal_required
    async def get(self):
        self.flash_success("foo")
        return self.redirect("/groups")


class PingSendGroupPage(AuthPage):
    @login_required
    @internal_required
    async def post(self):
        message = self.get_argument("message", None)
        group = self.model_by_id(GroupModel, "group_id")

        if not message:
            raise tornado.web.HTTPError(400)

        message = "{} ({})".format(
            message, self.current_user.main_character.character_name)

        await slack.group_ping(group.slug, message)

        app_log.info(
            "%s sent group ping to %s: %s" % (
                self.current_user, group, message)
        )

        return self.redirect(
            "/ping/send_group/success?group_id={}".format(group.id))


class PingSendGroupSuccessPage(AuthPage):
    @login_required
    @internal_required
    async def get(self):
        return self.redirect("/groups")


class SpecOpsPage(AuthPage):
    @login_required
    @internal_required
    @special_required
    async def get(self):
        return self.render(
            "specops.html"
        )


class HRPage(AuthPage):
    @login_required
    @internal_required
    @hr_required
    async def get(self):
        return self.render(
            "hr.html"
        )


class FCPage(AuthPage):
    @login_required
    @internal_required
    @fc_required
    async def get(self):
        return self.render(
            "fc.html"
        )


class FCFitsPage(AuthPage):
    @login_required
    @internal_required
    @fc_required
    async def get(self):
        return self.render(
            "fc_fits.html"
        )


class FCFitsResultPage(AuthPage):
    @login_required
    @internal_required
    @fc_required
    async def post(self):
        fit = self.get_argument("fit")

        items = parse_fit(fit)
        required_skills = dict()

        for item in items:
            for r in skills_item(item):
                required_skills[r[2]] = r[4]

        characters = {}
        character_models = session.query(CharacterModel).all()
        total = 0

        for character_model in character_models:
            if not character_model.is_internal:
                continue
            total += 1

            for character_skill in character_model.skills:
                if not character_skill.eve_skill.eve_id in required_skills.keys():
                    continue

                if character_skill.level >= required_skills[character_skill.eve_skill.eve_id]:
                    characters[character_model] = characters.get(character_model, [])
                    characters[character_model].append(True)

        can_fly = 0
        for character in characters:
            if len(characters[character]) == len(required_skills):
                can_fly += 1

        return self.render(
            "fc_fits_result.html",
            can_fly=can_fly,
            total=total,
            fit=fit
        )


class AdminPage(AuthPage):
    @login_required
    @internal_required
    @admin_required
    async def get(self):
        characters = list(session.query(CharacterModel).all())
        users = list(session.query(UserModel).all())
        memberships = list(session.query(MembershipModel).all())

        glance_total = len(characters)
        glance_internal = len(
            [character for character in characters if character.is_internal])
        glance_user = len(
            [user for user in users if user.is_internal])
        glance_membership = len(
            [membership for membership in memberships if membership.pending])

        return self.render(
            "admin.html",
            glance_total=glance_total,
            glance_internal=glance_internal,
            glance_user=glance_user,
            glance_membership=glance_membership
        )


class AdminGroupsPage(AuthPage):
    @login_required
    @internal_required
    @admin_required
    async def get(self):
        groups = session.query(GroupModel).all()

        return self.render("admin_groups.html", groups=groups)


class AdminGroupsManagePage(AuthPage):
    @login_required
    @internal_required
    @admin_required
    async def get(self):
        group = self.model_by_id(GroupModel, "group_id")

        self.render("admin_groups_manage.html", group=group)


class AdminGroupsSlackUpkeepPage(AuthPage):
    @login_required
    @internal_required
    @admin_required
    async def post(self):
        group = self.model_by_id(GroupModel, "group_id")

        await slack.group_upkeep(group)

        self.flash_success(
            self.locale.translate("GROUP_SLACK_UPKEEP_SUCCESS_ALERT"))
        self.redirect("/admin/groups/manage?group_id={}".format(group.id))


class AdminMembershipAllowPage(AuthPage):
    @login_required
    @internal_required
    @admin_required
    async def post(self):
        membership = self.model_by_id(MembershipModel, "membership_id")
        membership.pending = 0

        for identity in membership.user.slack_identities:
            member = await slack.user_email_to_id(identity.email)
            await slack.group_invite(membership.group.slug, member)

        session.add(membership)
        session.commit()

        self.flash_success(
            self.locale.translate("MEMBERSHIP_ALLOW_SUCCESS_ALERT"))
        self.redirect(
            "/admin/groups/manage?group_id={}".format(membership.group.id))


class AdminMembershipDenyPage(AuthPage):
    @login_required
    @internal_required
    @admin_required
    async def post(self):
        membership = self.model_by_id(MembershipModel, "membership_id")

        group_id = membership.group.id

        for identity in membership.user.slack_identities:
            member = await slack.user_email_to_id(identity.email)
            await slack.group_kick(membership.group.slug, member)

        session.delete(membership)
        session.commit()

        self.flash_success(
            self.locale.translate("MEMBERSHIP_DENY_SUCCESS_ALERT"))
        self.redirect("/admin/groups/manage?group_id={}".format(group_id))


class AdminGroupsCreatePage(AuthPage):
    @login_required
    @internal_required
    @admin_required
    async def post(self):
        # XXX check if already exists
        group = GroupModel()

        group.name = self.get_argument("group_name")
        group.slug = self.get_argument("group_slug")
        group.description = self.get_argument("group_description")
        group.has_slack = self.get_argument("group_has_slack")
        group.requires_approvial = self.get_argument("group_requires_approval")

        session.add(group)
        session.commit()

        self.flash_success(self.locale.translate("GROUP_ADD_SUCCESS_ALERT"))

        self.redirect("/admin/groups")


class AdminUsersPage(AuthPage):
    @login_required
    @internal_required
    @admin_required
    async def get(self):
        users = session.query(UserModel).all()
        users = sorted(users, key=lambda x: x.main_character.character_name)

        return self.render("admin_users.html", users=users)


class AdminUsersDetailPage(AuthPage):
    @login_required
    @internal_required
    @admin_required
    async def get(self):
        user = self.model_by_id(UserModel, "user_id")

        return self.render("admin_users_detail.html", user=user)


class AdminCharactersPage(AuthPage):
    @login_required
    @internal_required
    @admin_required
    async def get(self):
        # FIXME all of this is very naive and slow for large numbers of
        # characters, move most of the filtering to the database and paginate
        # the result set

        characters = session.query(CharacterModel).order_by(
            CharacterModel.character_name).all()

        filter_ship = self.get_argument("ship", None)
        filter_system = self.get_argument("system", None)
        filter_main = self.get_argument("main", None)

        if filter_ship:
            filter_ship = filter_ship.split("|")

            characters = [character for character in characters if character.last_ship]
            characters = [character for character in characters if character.last_ship.eve_type.eve_name in filter_ship]

        if filter_system:
            filter_system = filter_system.split("|")

            characters = [character for character in characters if character.last_location]
            characters = [character for character in characters if character.last_location.system.eve_name in filter_system]

        if filter_main:
            filter_main = filter_main.split("|")

            characters = [character for character in characters if character.user.main_character.character_name]
            characters = [character for character in characters if character.user.main_character.character_name in filter_main]

        return self.render("admin_characters.html", characters=characters)


class AdminCharactersDetailPage(AuthPage):
    @login_required
    @internal_required
    @admin_required
    async def get(self):
        character = self.model_by_id(CharacterModel, "character_id")

        return self.render("admin_characters_detail.html", character=character)


class APIAdminCharactersAutoCompletePage(AuthPage):
    @login_required
    @internal_required
    @admin_required
    async def get(self):
        # XXX naive
        query = self.get_argument("query", None)

        if not query:
            return self.write({"status": "success", "result": []})

        characters = session.query(CharacterModel).order_by(
            CharacterModel.character_name).all()

        characters = [character for character in characters if character.character_name.startswith(query)]

        return self.write({"status": "success", "result": [
            {"character_id": character.id,
             "character_name": character.character_name} for character in characters
        ]})


class APIAdminShipsAutoCompletePage(AuthPage):
    @login_required
    @internal_required
    @admin_required
    async def get(self):
        # XXX very naive
        query = self.get_argument("query", None)

        if not query:
            return self.write({"status": "success", "result": []})

        characters = session.query(CharacterModel).order_by(
            CharacterModel.character_name).all()

        characters = [character for character in characters if character.last_ship]

        ships = set(character.last_ship.eve_type for character in characters if character.last_ship.eve_type.eve_name.startswith(query))

        return self.write({"status": "success", "result": [
            {"ship_id": ship.id,
             "ship_name": ship.eve_name} for ship in ships
        ]})


class APIAdminSystemsAutoCompletePage(AuthPage):
    @login_required
    @internal_required
    @admin_required
    async def get(self):
        # XXX naive
        query = self.get_argument("query", None)

        if not query:
            return self.write({"status": "success", "result": []})

        systems = session.query(EVESolarSystemModel).all()
        systems = [system for system in systems if system.eve_name.startswith(query)]

        return self.write({"status": "success", "result": [
            {"system_id": system.id,
             "system_name": system.eve_name} for system in systems
        ]})
