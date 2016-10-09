from apoptosis.audit import (
	user,
	security
)

class AuditProxy:
	def __init__(self, settings=""):
		self.user = user
		self.security = security
