from anoikis.api.crest import characters as crest_characters

from apoptosis.models import session
from apoptosis.models import UserModel, CharacterLocationHistory, EVESolarSystemModel

from apoptosis import queue


def setup():
    for user in session.query(UserModel).all():
        setup_user(user)

def setup_user(user):
    for character in user.characters:
        setup_character(character)

def setup_character(character):
    queue.add_recurring(15, refresh_character_location, character)
    queue.add_recurring(300, refresh_character, character)

def refresh_character_location(character):
    system = crest_characters.character_location(character.character_id, character.access_token)

    if not system:
        return

    system = EVESolarSystemModel.from_id(system)

    if len(character.location_history) and system is character.location_history[-1]:
        return

    history_entry = CharacterLocationHistory(character, system)

    session.add(history_entry)
    session.commit()

    print(character.location_history[-2].when, character.location_history[-1].when)

def refresh_character(character):
    print("refreshing character", character)
