import random

import celery

from anoikis.api.eve.esi import characters as esi_characters
from anoikis.api.exceptions import InvalidToken

from apoptosis.models import session 
from apoptosis.models import UserModel, CharacterModel, CharacterLocationHistory, EVESolarSystemModel
from apoptosis.models import CharacterCorporationHistory, EVECorporationModel, EVETypeModel, CharacterShipHistory
from apoptosis.models import CharacterSkillModel, EVESkillModel

from apoptosis.queue.celery import celery_queue

from apoptosis.log import eve_log, job_log

from apoptosis.eve.sso import refresh_access_token

from datetime import datetime


def setup():
    job_log.info("user.setup")

    for user in session.query(UserModel).all():
        setup_user(user)

def setup_user(user):
    job_log.debug("user.setup_user {}".format(user))

    for character in user.characters:
        setup_character(character)

def setup_character(character):
    job_log.debug("user.setup_character {}".format(character.character_name))

    refresh_character_location.apply_async(args=(character.id,), countdown=random.randint(0, 120))
    refresh_character_ship.apply_async(args=(character.id,), countdown=random.randint(0, 120))
    refresh_character_corporation.apply_async(args=(character.id,), countdown=random.randint(0, 120))
    refresh_character_skills.apply_async(args=(character.id,), countdown=random.randint(0, 120))

@celery_queue.task(ignore_result=True)
def refresh_character_location(character_id, recurring=30):
    """Refresh a characters current location."""

    character = session.query(CharacterModel).filter(CharacterModel.id==character_id).one()

    job_log.debug("user.refresh_character_location {}".format(character.character_name))

    try:
        system_id = esi_characters.location(character.character_id, access_token=character.access_token)
    except InvalidToken:
        refresh_access_token(character)
        system_id = esi_characters.location(character.character_id, access_token=character.access_token)

    if system_id is not None:
        system_id = system_id["solar_system_id"]
        system = EVESolarSystemModel.from_id(system_id)

        if len(character.location_history) and system.id is character.location_history[-1].system_id:
            # don't update location history if the user is still in the same system
            pass
        else:
            history_entry = CharacterLocationHistory(character, system)
            eve_log.info("{} moved to {}".format(character.character_name, system.eve_name))
            session.add(history_entry)

    session.commit()

    if recurring:
        refresh_character_location.apply_async(args=(character_id, recurring), countdown=recurring)

@celery_queue.task(ignore_result=True)
def refresh_character_ship(character_id, recurring=60):
    """Refresh a characters current ship."""
    character = session.query(CharacterModel).filter(CharacterModel.id==character_id).one()

    job_log.debug("user.refresh_character_ship {}".format(character.character_name))

    try:
        type_id = esi_characters.ship(character.character_id, access_token=character.access_token)
    except InvalidToken:
        refresh_access_token(character)
        type_id = esi_characters.ship(character.character_id, access_token=character.access_token)

    if type_id is not None:
        item_id = type_id["ship_item_id"]
        type_id = type_id["ship_type_id"]

        eve_type = EVETypeModel.from_id(type_id)

        if len(character.ship_history) and character.ship_history[-1].eve_type == eve_type:
            pass
        else:
            eve_log.info("{} boarded {}".format(character.character_name, eve_type.eve_name))

            history_entry = CharacterShipHistory(character, eve_type)
            history_entry.eve_item_id = item_id

            session.add(history_entry)

        session.commit()

    if recurring:
        refresh_character_ship.apply_async(args=(character_id, recurring), countdown=recurring)


@celery_queue.task(ignore_result=True)
def refresh_character_corporation(character_id, recurring=3600):
    character = session.query(CharacterModel).filter(CharacterModel.id==character_id).one()

    job_log.debug("user.refresh_character_corporation {}".format(character.character_name))

    corporation_id = esi_characters.detail(character.character_id)

    if corporation_id is not None:
        corporation_id = corporation_id["corporation_id"]

        corporation = EVECorporationModel.from_id(corporation_id)

        if not len(character.corporation_history):
            # This character has no corp history at all
            session_entry = CharacterCorporationHistory(character, corporation)
            session_entry.join_date = datetime.now()  # XXX fetch this from the actual join date?
            session.add(session_entry)
            session.commit()
            return
        elif len(character.corporation_history) and character.corporation_history[-1].corporation is corporation:
            # Character is still in the same corporation as the last time we checked, we need to do nothing
            return
        elif len(character.corporation_history) and character.corporation_history[-1].corporation is not corporation:
            # Character changed corporation, close the last one and create a new one
            previously = character.corporation_history[-1]
            previously.exit_date = datetime.now()

            currently = CharacterCorporationHistory(character, corporation)
            currently.join_date = datetime.now()
            
            session.add(currently)
            session.add(previously)

            session.commit()

            eve_log.info("{} changed corporations {} -> {}".format(
                character.character_name,
                previously.corporation.name,
                currently.corporation.name)
            )

    if recurring:
        refresh_character_corporation.apply_async(args=(character_id, recurring), countdown=recurring)

@celery_queue.task(ignore_result=True)
def refresh_character_skills(character_id, recurring=14400):
    character = session.query(CharacterModel).filter(CharacterModel.id==character_id).one()

    job_log.debug("user.refresh_character_skills {}".format(character.character_name))

    try:
        skills = esi_characters.skills(character.character_id, access_token=character.access_token)
    except InvalidToken:
        refresh_access_token(character)
        skills = esi_characters.skills(character.character_id, access_token=character.access_token)

    if "skills" in skills:
        skills = skills["skills"]

        for skill in skills:
            skill_id = skill["skill_id"]

            eveskill = EVESkillModel.from_id(skill_id)

            session.add(eveskill)
            session.commit()

            skill_level = skill["current_skill_level"]
            skill_points = skill["skillpoints_in_skill"]

            characterskill = session.query(CharacterSkillModel).filter(
                CharacterSkillModel.character_id==character.id,
                CharacterSkillModel.eve_skill_id==eveskill.id
            ).one_or_none()

            if characterskill is None:
                characterskill = CharacterSkillModel(character)
                characterskill.eve_skill = eveskill

            # XXX notify change?
            characterskill.level = skill_level
            characterskill.points = skill_points

            session.add(characterskill)
            session.commit()

    if recurring:
        refresh_character_corporation.apply_async(args=(character_id, recurring), countdown=recurring)

def refresh_character(character_id):
    pass
