from hkauth.audit.base import message


def succesful_registration(request, user):
	message("Succesful registration for {}".format(user.email))

def succesful_login(request, user):
	message("Succesful login for {}".format(user.email))

def succesful_logout(request, user):
	message("Succesful logout for {}".format(user.email))
