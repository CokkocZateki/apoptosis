import tornado.web
import tornado.locale
import tornado.ioloop

from apoptosis.http.pages import (
    HomePage,
    LoginPage,
    LoginCallbackPage,
    LoginSuccessPage,
    LoginCreatedPage,
    LogoutPage,
    LogoutSuccessPage,
    CharactersPage,
    CharactersSelectMainPage,
    CharactersSelectMainSuccessPage,
    ServicesPage,
    ServicesDeleteSlackIdentityPage,
    ServicesAddSlackIdentityPage,
    ServicesAddSlackIdentitySuccessPage,
    ServicesSendVerificationSlackIdentityPage,
    ServicesVerifyVerificationSlackIdentityPage,
    ServicesVerifySlackIdentitySuccessPage,
    GroupsPage,
    GroupsJoinPage,
    GroupsJoinSuccessPage,
    GroupsLeavePage,
    GroupsLeaveSuccessPage,
    PingPage,
    PingSendAllPage,
    PingSendAllSuccessPage,
    PingSendGroupPage,
    PingSendGroupSuccessPage,
    AdminPage,
    AdminGroupsPage,
    AdminGroupsCreatePage,
    AdminGroupsManagePage,
    AdminMembershipAllowPage,
    AdminMembershipDenyPage,
    AdminUsersPage,
    AdminCharactersPage,
    AdminCharactersPage,
)

from apoptosis import config
from apoptosis.queue import user as queue_user
from apoptosis.log import app_log


def make_app():

    return tornado.web.Application([
            (
                r"/",
                HomePage
            ),
            (
                r"/characters",
                CharactersPage
            ),
            (
                r"/characters/select_main",
                CharactersSelectMainPage
            ),
            (
                r"/characters/select_main/success",
                CharactersSelectMainSuccessPage
            ),
            (
                r"/services",
                ServicesPage
            ),
            (
                r"/services/delete_slack_identity",
                ServicesDeleteSlackIdentityPage
            ),
            (
                r"/services/add_slack_identity",
                ServicesAddSlackIdentityPage
            ),
            (
                r"/services/add_slack_identity/success",
                ServicesAddSlackIdentitySuccessPage
            ),
            (
                r"/services/send_slack_verification",
                ServicesSendVerificationSlackIdentityPage
            ),
            (
                r"/services/verify_slack_verification",
                ServicesVerifyVerificationSlackIdentityPage
            ),
            (
                r"/services/verify_slack_verification/success",
                ServicesVerifySlackIdentitySuccessPage
            ),
            (
                r"/groups",
                GroupsPage
            ),
            (
                r"/groups/join",
                GroupsJoinPage
            ),
            (
                r"/groups/join/success",
                GroupsJoinSuccessPage
            ),
            (
                r"/groups/leave",
                GroupsLeavePage
            ),
            (
                r"/groups/leave/success",
                GroupsLeaveSuccessPage
            ),
            (
                r"/ping",
                PingPage
            ),
            (
                r"/ping/send_all",
                PingSendAllPage
            ),
            (
                r"/ping/send_group",
                PingSendGroupPage
            ),
            (
                r"/ping/send_all/success",
                PingSendAllSuccessPage
            ),
            (
                r"/ping/send_group/success",
                PingSendGroupSuccessPage
            ),
            (
                r"/admin",
                AdminPage 
            ),
            (
                r"/admin/groups",
                AdminGroupsPage 
            ),
            (
                r"/admin/groups/create",
                AdminGroupsCreatePage 
            ),
            (
                r"/admin/groups/manage",
                AdminGroupsManagePage 
            ),
            (
                r"/admin/groups/membership/allow",
                AdminMembershipAllowPage
            ),
            (
                r"/admin/groups/membership/deny",
                AdminMembershipDenyPage
            ),
            (
                r"/admin/users",
                AdminUsersPage 
            ),
            (
                r"/admin/characters",
                AdminCharactersPage 
            ),
            (
                r"/login",
                LoginPage
            ),
            (
                r"/login/eve-sso-callback",
                LoginCallbackPage
            ),
            (
                r"/login/success",
                LoginSuccessPage
            ),
            (
                r"/login/created",
                LoginCreatedPage
            ),
            (
                r"/logout",
                LogoutPage
            ),
            (
                r"/logout/success",
                LogoutSuccessPage
            ),
            (
                r"/static/(.*)",
                tornado.web.StaticFileHandler,
                {"path": config.tornado_static}
            ),
        ],
        template_path=config.tornado_templates,
        cookie_secret=config.tornado_secret,
        debug=True
    )

def main():
    app_log.info("starting application")

    app = make_app()
    app.listen(config.http_port)

    start_queues = False
    if start_queues:
        queue_user.setup()

    tornado.locale.load_translations(config.tornado_translations)
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
