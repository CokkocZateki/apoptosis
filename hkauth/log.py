import logging
import sys

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

channel = logging.StreamHandler(sys.stdout)
channel.setLevel(logging.DEBUG)
channel.setFormatter(formatter)

root = logging.getLogger()
root.setLevel(logging.DEBUG)

root.addHandler(channel)

app_log = logging.getLogger("hkauth.application")
sec_log = logging.getLogger("hkauth.security")
svc_log = logging.getLogger("hkauth.services")
