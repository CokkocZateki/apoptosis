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
from apoptosis.eve import xml as xml_api
from apoptosis.eve import crest as crest_api
from apoptosis import config


engine = create_engine(config.database_uri)
session = scoped_session(sessionmaker(autocommit=False,
                                      autoflush=False,
                                      bind=engine))


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
    is_special = Column(Boolean)
    is_hr = Column(Boolean)

    @property
    def is_internal(self):
        # If any character on any active SSO or API token is in the
        # configured alliance or corp then this is an internal user
        # who has access to all features
        return any(c.is_internal for c in self.characters)

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

    def __repr__(self):
        return "<UserModel(id={}) {}>".format(self.id, self.main_character)


class UserLoginModel(Base):
    pub_date = Column(DateTime)

    user_id = Column(Integer, ForeignKey("user.id"))
    user = relationship("UserModel", backref="logins")

    ip_address = Column(String)


crestscope_x_character = Table(
    "x_crestscope_character",
    Base.metadata,
    Column("crestscope_id", Integer, ForeignKey("crestscope.id")),
    Column("character_id", Integer, ForeignKey("character.id"))
)


class CRESTScopeModel(Base):
    name = Column(String)

    characters = relationship(
        "CharacterModel",
        secondary=crestscope_x_character,
        backref="crest_scopes"
    )

    def __init__(self, name):
        self.name == name


class CharacterModel(Base):
    user_id = Column(Integer, ForeignKey("user.id"))
    user = relationship("UserModel", backref="characters")

    is_main = Column(Boolean)

    account_hash = Column(String)

    refresh_token = Column(String)
    access_token = Column(String)

    character_id = Column(Integer)
    character_name = Column(String)

    corporation_id = Column(Integer)
    corporation_name = Column(String)

    alliance_id = Column(Integer)
    alliance_name = Column(String)

    def update_scopes(self, character_scopes):
        for crestscope in character_scopes:
            crestscope_model = session.query(CRESTScopeModel).filter(CRESTScopeModel.name==crestscope).first()

            if not crestscope_model:
                crestscope_model = CRESTScopeModel(crestscope)

            self.crest_scopes.append(crestscope_model)


    @classmethod
    async def from_xml_api(cls, character_id):
        """Instantiate a new character model from the public EVE XML
           API through its character id."""

        instance = cls()

        response = await xml_api.character(character_id)

        instance.character_id = response["character_id"]
        instance.character_name = response["character_name"]

        instance.corporation_id = response["corporation_id"]
        instance.corporation_name = response["corporation_name"]

        instance.alliance_id = response["alliance_id"]
        instance.alliance_name = response["alliance_name"]

        return instance

    @property
    def is_online(self):
        return len(self.session_history) and self.session_history[-1].sign_out is None

    @property
    def last_location(self):
        if len(self.location_history):
            return self.location_history[-1]
        else:
            return None

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
        return self.corporation_name == "Hard Knocks Inc."  # XXX get from config

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

class CharacterSessionHistory(Base):
    character_id = Column(Integer, ForeignKey("character.id"))
    character = relationship("CharacterModel", backref="session_history")

    sign_in = Column(DateTime)
    sign_out = Column(DateTime)

    def __init__(self, character):
        self.character = character


class GroupModel(Base):
    name = Column(String)
    slug = Column(String)

    description = Column(Text)

    has_slack = Column(Boolean)
    has_ts3 = Column(Boolean)

    requires_approval = Column(Boolean)

    def ts3_upkeep(self):
        ts3.group_upkeep(self.slug)

    def slack_upkeep(self):
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


class TS3IdentityModel(Base):
    user_id = Column(Integer, ForeignKey("user.id"))
    user = relationship("UserModel", backref="ts3_identities")

    identity = Column(String)

    def __init__(self, identity):
        self.identity = identity


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
        self.verification_code = hashlib.sha256(os.urandom(4)).hexdigest()

    def verify(self):
        if slack.verify_identity(self.email):
            self.verification_sent = True


class EVESolarSystemModel(Base):
    eve_id = Column(Integer)
    eve_name = Column(String)

    @classmethod
    def from_id(cls, eve_id):
        instance = session.query(cls).filter(cls.eve_id==eve_id).first()

        if not instance:
            instance = cls()
            instance.eve_id = eve_id

        return instance


class EVECharacterModel(Base):
    eve_id = Column(Integer)
    eve_name = Column(String)


class EVECorporationModel(Base):
    eve_id = Column(Integer)
    name = Column(String)

    @classmethod
    def from_id(cls, eve_id):
        instance = session.query(cls).filter(cls.eve_id==eve_id).first()

        if not instance:
            instance = cls()
            instance.eve_id = eve_id

        return instance


class EVEAllianceModel(Base):
    eve_id = Column(Integer)
    eve_name = Column(String)


class LocalScanModel(Base):
    raw = Column(Text)


class LocalScanMembershipModel(Base):
    character_id = Column(Integer, ForeignKey("evecharacter.id"))
    character = relationship("EVECharacterModel", backref="characters")

    system_id = Column(Integer, ForeignKey("evesolarsystem.id"))
    system = relationship("EVESolarSystemModel", backref="systems")

    when = Column(DateTime)


if __name__ == '__main__':
    Base.metadata.create_all(engine)
