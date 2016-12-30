import logging
import sys

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

channel = logging.StreamHandler(sys.stdout)
channel.setLevel(logging.DEBUG)
channel.setFormatter(formatter)

root = logging.getLogger()
root.setLevel(logging.DEBUG)

root.addHandler(channel)

app_log = logging.getLogger("apoptosis.application")
sec_log = logging.getLogger("apoptosis.security")
svc_log = logging.getLogger("apoptosis.services")
eve_log = logging.getLogger("apoptosis.eve")
job_log = logging.getLogger("apoptosis.jobs")
