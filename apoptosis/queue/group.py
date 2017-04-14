import random

import tornado.ioloop

from datetime import datetime

from apoptosis.models import session 
from apoptosis.models import GroupModel

from apoptosis.log import eve_log, job_log

from apoptosis.queue.celery import celery_queue

from apoptosis.services import slack


def start_slack():
    tornado.ioloop.IOLoop.current().run_sync(slack.refresh_user_email_to_ids)

def setup():
    job_log.info("group.setup")

    tornado.ioloop.IOLoop.current().run_sync(slack.refresh_user_email_to_ids)

    for group in session.query(GroupModel).all():
        setup_group(group)

def setup_group(group):
    job_log.debug("group.setup_group {}".format(group))

    refresh_group_members.apply_async(args=(group.id,), countdown=random.randint(0,300))

    if group.has_slack:
        refresh_group_slack.apply_async(args=(group.id,), countdown=random.randint(0,300))

@celery_queue.task(ignore_result=True)
def refresh_group_members(group_id, recurring=60):
    """Refresh a group and kick any members that are not internal."""

    group = session.query(GroupModel).filter(GroupModel.id==group_id).one()

    job_log.debug("group.refresh_group_members {}".format(group))

    for membership in group.memberships:
        if not membership.user.is_internal:
            job_log.warn("group.refresh_group_members removing {} from {} no_internal".format(membership.user, group))

            session.delete(membership)
            session.commit()

    if recurring:
        refresh_group_members.apply_async(args=(group_id, recurring), countdown=recurring)


@celery_queue.task(bind=True, ignore_result=True, default_retry_delay=300)
def refresh_group_slack(self, group_id, recurring=300):
    """Refresh a group's slack channel."""
    try:
        group = session.query(GroupModel).filter(GroupModel.id==group_id).one()

        tornado.ioloop.IOLoop.current().run_sync(lambda: slack.group_upkeep(group))

        if recurring:
            refresh_group_slack.apply_async(args=(group_id, recurring), countdown=recurring)
    except Exception as e:
        self.retry(exc=e)
