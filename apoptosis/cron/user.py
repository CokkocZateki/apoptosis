from anoikis.api.crest import characters as crest_characters

from apoptosis.models import session
from apoptosis.models import UserModel, CharacterLocationHistory, CharacterSessionHistory, EVESolarSystemModel

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
    queue.add_recurring(300, refresh_character, character)

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

        if len(character.location_history) and system is character.location_history[-1]:
            # don't update location history if the user is still in the same system
            pass
        else:
            history_entry = CharacterLocationHistory(character, system)

            eve_log.debug("{} moved to {}".format(character.character_name, system.eve_name))

            session.add(history_entry)
            
        session.commit()

def refresh_character(character):
    pass
