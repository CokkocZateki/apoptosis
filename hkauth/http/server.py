import tornado.web
import tornado.locale
import tornado.ioloop

from hkauth.http.pages import (
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
    ServicesAddTS3IdentityPage,
    ServicesAddTS3IdentitySuccessPage,
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
    AdminUsersPage
)

from hkauth import config


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
                r"/services/add_teamspeak_identity",
                ServicesAddTS3IdentityPage
            ),
            (
                r"/services/add_teamspeak_identity/success",
                ServicesAddTS3IdentitySuccessPage
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
                r"/admin/users",
                AdminUsersPage 
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
    app = make_app()
    app.listen(config.http_port)
    tornado.locale.load_translations(config.tornado_translations)
    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
