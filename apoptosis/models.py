import os

import hashlib

from sqlalchemy import BigInteger, Integer, Column, String, DateTime, ForeignKey, UniqueConstraint, Float, Boolean
from sqlalchemy import create_engine, Text, Table, Boolean, func

from sqlalchemy.orm import relationship, backref, joinedload
from sqlalchemy.orm import backref, sessionmaker, scoped_session

from sqlalchemy.ext.declarative import declarative_base, declared_attr

from datetime import datetime

from apoptosis.exceptions import InvalidAPIKey

from apoptosis.services import slack
from apoptosis import config

import anoikis.api.eve as eve_api

from anoikis.api.eve.esi import characters as esi_characters

from anoikis.static.systems import system_name
from anoikis.static.items import item_name


engine = create_engine(config.database_uri)
session = scoped_session(sessionmaker(autocommit=False,
                                      autoflush=False,
                                      bind=engine))

# XXX TODO MOVE TO CONFIG
GROUP_MAP = {
    "directors": "directors",
    "specops": "specops",
    "hr": "hr"
}


class Base(object):
    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower().replace("model", "")

    id = Column(Integer, primary_key=True)


Base = declarative_base(cls=Base)


class UserModel(Base):
    pub_date = Column(DateTime)
    chg_date = Column(DateTime)

    is_admin = Column(Boolean)

    @property
    def is_internal(self):
        # If any character on any active SSO or API token is in the
        # configured alliance or corp then this is an internal user
        # who has access to all features
        return any(c.is_internal for c in self.characters)

    @property
    def is_special(self):
        if self.is_admin:
            return True

        return False

    @property
    def is_hr(self):
        if self.is_admin:
            return True

        return False

    @property
    def is_fc(self):
        if self.is_admin:
            return True

        return False

    @property
    def main_character(self):
        for character in self.characters:
            if character.is_main:
                return character

    @property
    def groups(self):
        return [membership.group for membership in self.memberships if not membership.pending]

    @property
    def last_login(self):
        return session.query(UserLoginModel).filter(UserLoginModel.user_id==self.id).order_by(UserLoginModel.pub_date.desc()).first()

    @property
    def sp(self):
        return sum(character.sp for character in self.characters)

    def __repr__(self):
        return "<UserModel(id={}) {}>".format(self.id, self.main_character)


class UserLoginModel(Base):
    pub_date = Column(DateTime)

    user_id = Column(Integer, ForeignKey("user.id"))
    user = relationship("UserModel", backref="logins")

    ip_address = Column(String)


esiscope_x_character = Table(
    "x_esiscope_character",
    Base.metadata,
    Column("esiscope_id", Integer, ForeignKey("esiscope.id")),
    Column("character_id", Integer, ForeignKey("character.id"))
)


class ESIScopeModel(Base):
    name = Column(String)

    characters = relationship(
        "CharacterModel",
        secondary=esiscope_x_character,
        backref="esi_scopes"
    )

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return "ESIScopeModel({})".format(self.name)

class CharacterModel(Base):
    user_id = Column(Integer, ForeignKey("user.id"))
    user = relationship("UserModel", backref="characters")

    is_main = Column(Boolean)

    account_hash = Column(String)

    refresh_token = Column(String)
    access_token = Column(String)

    character_id = Column(BigInteger)
    character_name = Column(String)

    alliance_id = Column(BigInteger)
    alliance_name = Column(String)

    def update_scopes(self, character_scopes):
        for esiscope in character_scopes:
            esiscope_model = session.query(ESIScopeModel).filter(ESIScopeModel.name==esiscope).first()

            if not esiscope_model:
                esiscope_model = ESIScopeModel(esiscope)

            self.esi_scopes.append(esiscope_model)

    @classmethod
    async def from_api(cls, character_id):
        """Instantiate a new character model from the public EVE ESI
           API through its character id."""

        instance = cls()

        character = esi_characters.detail(character_id) # XXX replace fully

        instance.character_id = character_id
        instance.character_name = character["name"]

        corporation = EVECorporationModel.from_id(character["corporation_id"])

        history_entry = CharacterCorporationHistory(instance, corporation)
        history_entry.join_date = datetime.now()  # XXX fetch this from the actual join date?

        if "alliance_id" in character:
            # XXX history instance
            alliance = eve_api.alliance_detail(character["alliance_id"])

            instance.alliance_id = character["alliance_id"]
            instance.alliance_name = alliance["alliance_name"]

        return instance

    @property
    def corporation(self):
        if len(self.corporation_history):
            return self.corporation_history[-1].corporation
        else:
            return None

    @property
    def is_online(self):
        print(self.session_history)
        return len(self.session_history) and self.session_history[-1].sign_out is None

    @property
    def last_location(self):
        if len(self.location_history):
            return self.location_history[-1]
        else:
            return None

    @property
    def last_ship(self):
        if len(self.ship_history):
            return self.ship_history[-1]
        else:
            return None

    @property
    def sp(self):
        return sum(s.points for s in self.skills)

    @property
    def has_public_scopes(self):
        return True  # XXX get from scopesets

    @property
    def has_internal_scopes(self):
        return True  # XXX get from scopesets

    def __eq__(self, other):
        if not other:
            return False

        return other.user == self.user and other.character_id == self.character_id


    def __hash__(self):
        return hash((self.user.id, self.character_id))

    @property
    def is_internal(self):
        return self.corporation.name == "Hard Knocks Inc." and self.is_valid  # XXX get from config

    @property
    def is_valid(self):
        return self.access_token is not None

    def __repr__(self):
        return "<CharacterModel(id={}) {}>".format(self.id, self.character_name)


class CharacterCorporationHistory(Base):
    character_id = Column(Integer, ForeignKey("character.id"))
    character = relationship("CharacterModel", backref="corporation_history")

    corporation_id = Column(Integer, ForeignKey("evecorporation.id"))
    corporation = relationship("EVECorporationModel")

    join_date = Column(DateTime)
    exit_date = Column(DateTime)

    def __init__(self, character, corporation):
        self.character = character
        self.corporation = corporation


class CharacterAllianceHistory(Base):
    character_id = Column(Integer, ForeignKey("character.id"))
    character = relationship("CharacterModel", backref="alliance_history")

    alliance_id = Column(Integer, ForeignKey("evealliance.id"))
    alliance = relationship("EVEAllianceModel")

    join_date = Column(DateTime)
    exit_date = Column(DateTime)

    def __init__(self, character, alliance):
        self.character = character
        self.alliance = alliance

class CharacterLocationHistory(Base):
    character_id = Column(Integer, ForeignKey("character.id"))
    character = relationship("CharacterModel", backref="location_history")

    system_id = Column(Integer, ForeignKey("evesolarsystem.id"))
    system = relationship("EVESolarSystemModel")

    when = Column(DateTime)

    def __init__(self, character, system):
        self.character = character
        self.system = system
        self.when = datetime.now()


class CharacterShipHistory(Base):
    character_id = Column(Integer, ForeignKey("character.id"))
    character = relationship("CharacterModel", backref="ship_history")

    eve_type_id = Column(Integer, ForeignKey("evetype.id"))
    eve_type = relationship("EVETypeModel")

    eve_item_id = Column(BigInteger)

    when = Column(DateTime)

    def __init__(self, character, eve_type):
        self.character = character
        self.eve_type = eve_type
        self.when = datetime.now()


class CharacterSessionHistory(Base):
    character_id = Column(Integer, ForeignKey("character.id"))
    character = relationship("CharacterModel", backref="session_history")

    sign_in = Column(DateTime)
    sign_out = Column(DateTime)

    def __init__(self, character):
        self.character = character


class CharacterSkillModel(Base):
    character_id = Column(Integer, ForeignKey("character.id"))
    character = relationship("CharacterModel", backref="skills")

    eve_skill_id = Column(Integer, ForeignKey("eveskill.id"))
    eve_skill = relationship("EVESkillModel")

    level = Column(BigInteger)

    points = Column(BigInteger)

    def __init__(self, character):
        self.character = character


class GroupModel(Base):
    name = Column(String)
    slug = Column(String)

    description = Column(Text)

    has_slack = Column(Boolean)

    requires_approval = Column(Boolean)

    def slack_upkeep(self):
        if self.has_slack:
            slack.group_upkeep(self.slug)

    @property
    def members(self):
        return [membership.user for membership in self.memberships if not membership.pending]

    def has_member(self, user):
        for membership in self.memberships:
            if membership.user == user and not membership.pending:
                return True

        return False

    def has_pending(self, user):
        for membership in self.memberships:
            if membership.user == user and membership.pending:
                return True

        return False

    def pending(self):
        return [membership for membership in self.memberships if membership.pending]

    def __repr__(self):
        return "<GroupModel(id={}) {}>".format(self.id, self.name)


class MembershipModel(Base):
    group_id = Column(Integer, ForeignKey("group.id"))
    group = relationship("GroupModel", backref="memberships")

    user_id = Column(Integer, ForeignKey("user.id"))
    user = relationship("UserModel", backref="memberships")

    pending = Column(Boolean)

    owner = Column(Boolean)
    moderator = Column(Boolean)


class SlackIdentityModel(Base):
    user_id = Column(Integer, ForeignKey("user.id"))
    user = relationship("UserModel", backref="slack_identities")

    email = Column(String)

    slack = Column(String)

    verification_done = Column(Boolean)
    verification_sent = Column(Boolean)
    verification_code = Column(String)

    def __init__(self, email):
        self.email = email
        self.verification_code = hashlib.sha256(os.urandom(4)).hexdigest()[:10].upper()

    def verify(self):
        if slack.verify_identity(self.email):
            self.verification_sent = True


class EVESolarSystemModel(Base):
    eve_id = Column(BigInteger)
    eve_name = Column(String)

    @classmethod
    def from_id(cls, eve_id):
        instance = session.query(cls).filter(cls.eve_id==eve_id).first()

        if not instance:
            instance = cls()
            instance.eve_id = eve_id
            instance.eve_name = system_name(eve_id)

        return instance


class EVETypeModel(Base):
    eve_id = Column(BigInteger)
    eve_name = Column(String)

    @classmethod
    def from_id(cls, eve_id):
        instance = session.query(cls).filter(cls.eve_id==eve_id).first()

        if not instance:
            instance = cls()
            instance.eve_id = eve_id
            instance.eve_name = item_name(eve_id)

        return instance


class EVECharacterModel(Base):
    eve_id = Column(BigInteger)
    name = Column(String)

    @classmethod
    def from_id(cls, eve_id):
        instance = session.query(cls).filter(cls.eve_id==eve_id).first()

        if not instance:
            instance = cls()
            instance.eve_id = eve_id

        return instance

class EVECorporationModel(Base):
    eve_id = Column(BigInteger)
    name = Column(String)

    @classmethod
    def from_id(cls, eve_id):
        instance = session.query(cls).filter(cls.eve_id==eve_id).first()

        if not instance:
            instance = cls()
            instance.eve_id = eve_id
            instance.name = eve_api.corporation_detail(eve_id)["corporation_name"]

        return instance


class EVESkillModel(Base):
    eve_id = Column(BigInteger)
    eve_name = Column(String)

    @classmethod
    def from_id(cls, eve_id):
        instance = session.query(cls).filter(cls.eve_id==eve_id).first()

        if not instance:
            instance = cls()
            instance.eve_id = eve_id
            instance.eve_name = item_name(eve_id)

        return instance


class EVEAllianceModel(Base):
    eve_id = Column(BigInteger)
    eve_name = Column(String)


class LocalScanModel(Base):
    raw = Column(Text)


class LocalScanMembershipModel(Base):
    character_id = Column(Integer, ForeignKey("evecharacter.id"))
    character = relationship("EVECharacterModel", backref="characters")

    system_id = Column(Integer, ForeignKey("evesolarsystem.id"))
    system = relationship("EVESolarSystemModel", backref="systems")

    when = Column(DateTime)


class NotificationTargetModel(Base):
    group_id = Column(Integer, ForeignKey("group.id"))
    group = relationship("GroupModel", backref="notification_targets")

    user_id = Column(Integer, ForeignKey("user.id"))
    user = relationship("UserModel", backref="notification_targets")


class SystemWatchModel(Base):
    group_id = Column(Integer, ForeignKey("group.id"))
    group = relationship("GroupModel", backref="system_watches")

    user_id = Column(Integer, ForeignKey("user.id"))
    user = relationship("UserModel", backref="system_watches")

    system_id = Column(Integer, ForeignKey("evesolarsystem.id"))
    system = relationship("EVESolarSystemModel")

    # XXX many-to-many with notification targets


class KillWatchModel(Base):
    group_id = Column(Integer, ForeignKey("group.id"))
    group = relationship("GroupModel", backref="kill_watches")

    user_id = Column(Integer, ForeignKey("user.id"))
    user = relationship("UserModel", backref="kill_watches")

    # XXX many-to-many with notification targets


if __name__ == '__main__':
    Base.metadata.create_all(engine)
