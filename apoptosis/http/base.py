import tornado.ioloop
import tornado.web
import base64

import json

from apoptosis.models import (
    session,
    UserModel
)

from apoptosis.log import app_log


class AuthPage(tornado.web.RequestHandler):
    def requires_login(self):
        if not self.current_user:
            raise tornado.web.HTTPError(401)

    def requires_internal(self):
        if not self.current_user.is_internal:
            raise tornado.web.HTTPError(403)

    def requires_admin(self):
        if not self.current_user.is_admin:
            raise tornado.web.HTTPError(403)

    def requires_hr(self):
        if not self.current_user.is_hr and not self.current_user.is_admin:
            raise tornado.web.HTTPError(403)

    def requires_special(self):
        if not self.current_user.is_special and not self.current_user.is_admin:
            raise tornado.web.HTTPError(403)

    def model_by_id(self, model, argument):
        """Fetch a model instance by its primary key from the arguments. We also
           verify if the current user is the owner of the model. XXX"""

        # XXX verify current owner of the model (if it has a relationship with user)
        model_id = self.get_argument(argument, None)

        if not model_id:
            raise tornado.web.HTTPError(404)

        instance = session.query(model).filter(model.id==model_id).first()

        if not instance:    
            raise tornado.web.HTTPError(404)

        if hasattr(instance, "user"):
            if not instance.user == self.current_user:
                raise tornado.web.HTTPError(403)

        return instance
        

    def write_error(self, status_code, **kwargs):
        return self.render("{}.html".format(status_code))

    def get_current_user(self):
        cookie = self.get_secure_cookie("user_id")

        if cookie:
            user_id = int(self.get_secure_cookie("user_id"))
        else:
            return None

        user = session.query(UserModel).filter(UserModel.id==user_id).first()

        if not user:
            # This was a cookie for a non-existing user
            app_log.warn("Cookie with id:{} was used to try to login but no user by that id".format(user_id))
            raise tornado.web.HTTPError(500)

        return user


    def set_current_user(self, user):
        if user is None:
            self.clear_cookie("user_id")
        else:
            return self.set_secure_cookie("user_id", str(user.id))

    def _flash(self, state, message):
        if not self.get_secure_cookie("flashes"):
            flashes = []
        else:
            flashes = json.loads(self.get_secure_cookie("flashes").decode("utf-8"))

        flashes.append({"state": state, "message": message})

        self.set_secure_cookie("flashes", json.dumps(flashes))

    def flash_success(self, message):
        self._flash("success", message)

    def flash_error(self, message):
        self._flash("error", message)

    def flash_messages(self):
        if not self.get_secure_cookie("flashes"):
            flashes = []
        else:
            flashes = json.loads(self.get_secure_cookie("flashes").decode("utf-8"))

        self.set_secure_cookie("flashes", json.dumps([]))

        return base64.b64encode(json.dumps(flashes).encode("utf-8"))
