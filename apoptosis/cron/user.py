from anoikis.api.crest import characters as crest_characters

from apoptosis.models import session
from apoptosis.models import UserModel, CharacterLocationHistory, CharacterSessionHistory, EVESolarSystemModel
from apoptosis.models import CharacterCorporationHistory, EVECorporationModel

from apoptosis import queue
from apoptosis.log import eve_log

from datetime import datetime


def setup():
    for user in session.query(UserModel).all():
        setup_user(user)

def setup_user(user):
    for character in user.characters:
        setup_character(character)

def setup_character(character):
    queue.add_recurring(15, refresh_character_online, character)
    queue.add_recurring(3600, refresh_character_corporation, character)

def refresh_character_online(character):
    """Refresh a characters online state and it's current location.
    
       XXX: maybe make a slower window the longer someone is offline?"""
    system = crest_characters.character_location(character.character_id, character.access_token)

    if not system:
        # char is currently offline lets see if we have an entry in the session
        # history that shows him as online and update that
        if len(character.session_history) and character.session_history[-1].sign_out is None:
            # update that record
            character.session_history[-1].sign_out = datetime.now()
            
            session.add(character)
            session.commit()

            eve_log.debug("{} signed out".format(character.character_name))
    else:
        # char is currently online. do we curently have an entry that shows
        # as online?
        if len(character.session_history) and character.session_history[-1].sign_out is None:
            # yep, continue
            pass
        else:
            # add a new session entry
            session_entry = CharacterSessionHistory(character)
            session_entry.sign_in = datetime.now()
            
            session.add(session_entry)

            eve_log.debug("{} signed in".format(character.character_name))

        system = EVESolarSystemModel.from_id(system)

        if len(character.location_history) and system.id is character.location_history[-1].id:
            # don't update location history if the user is still in the same system
            pass
        else:
            history_entry = CharacterLocationHistory(character, system)

            eve_log.debug("{} moved to {}".format(character.character_name, system.eve_name))

            session.add(history_entry)
            
        session.commit()

def refresh_character_corporation(character):
    corporation = crest_characters.character_corporation(character.character_id, character.access_token)
    corporation = EVECorporationModel.from_id(corporation)

    if not len(character.corporation_history):
        # This character has no corp history at all
        session_entry = CharacterCorporationHistory(character, corporation)
        session_entry.join_date = datetime.now()  # XXX fetch this from the actual join date?
        session.add(session_entry)
        session.commit()
        return
    elif len(character.corporation_history) and character.corporation_history[-1] is corporation:
        # Character is still in the same corporation as the last time we checked, we need to do nothing
        return
    elif len(character.corporation_history) and character.corporation_history[-1] is not corporation:
        # Character changed corporation, close the last one and create a new one
        previously = character.corporation_history[-1]
        previously.exit_date = datetime.now()

        currently = CharacterCorporationHistory(character, corporation)
        currently.join_date = datetime.now()
        
        session.add(currently)
        session.add(previously)

        session.commit()

        eve_log.debug("{} changed corporations {} -> {}".format(
            character.character_name,
            previously.corporation.name,
            currently.corporation.name)
        )

        return


def refresh_character(character):
    pass
