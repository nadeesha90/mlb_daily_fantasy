import numpy as np

from sqlalchemy import Column, String, Text, Integer, ForeignKey, Enum, DateTime, Float, PickleType, Boolean, func, select, join
from sqlalchemy.orm import relationship, backref
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.hybrid import hybrid_property, hybrid_method

from models.helpers import Base
from config import HardCoded


class Team(Base):
    __tablename__ = 'team'
    id = Column(Integer, primary_key=True)
    name = Column(String(80), unique=True)
    city = Column(String(80))
    cityAbbr = Column(String(3), unique=True)
    players = association_proxy('team_players', 'player')


class Player(Base):
    __tablename__ = 'player'
    id = Column(Integer, primary_key=True)
    mlbgame_id = Column(Integer)
    last_name = Column(String(80))
    full_name = Column(String(80))
    player_type = Column(Enum(*HardCoded.MLB_PlayerType))
    teams = association_proxy('team_players', 'team')

    @hybrid_property
    def pitcher_fd_fpts_avg(self):
        return np.mean([stat.fd_fpts for stat in self.pitcherstatlines])
    @pitcher_fd_fpts_avg.expression
    def pitcher_fd_fpts_avg(cls):
        return func.avg(PitcherStatLine.fd_fpts)
    @hybrid_property
    def batter_fd_fpts_avg(self):
        return np.mean([stat.fd_fpts for stat in self.batterstatlines])
    @batter_fd_fpts_avg.expression
    def batter_fd_fpts_avg(cls):
        return func.avg(BatterStatLine.fd_fpts)


class TeamPlayer(Base):
    __tablename__ = 'team_player'
    player_id = Column(Integer, ForeignKey('player.id'))
    team_id = Column(Integer, ForeignKey('team.id'))
    team_join_date = Column(DateTime)
    # bidirectional attribute/collection of "team"/"team_players"
    team = relationship(Team, backref=backref("team_players", cascade="all, delete-orphan"))
    player = relationship(Player, backref=backref("team_players", cascade="all, delete-orphan"))

    def __repr__(self):
        return 'TeamPlayer(team={},player={})'.format(self.team.name, self.player.full_name)


class Stadium(Base):
    __tablename__ = 'stadium'
    id = Column(Integer, primary_key=True)
    name = Column(String(80), unique=True)
    team_id = Column(Integer, ForeignKey('team.id'))
    team = relationship("Team",
                        backref=backref("stadiums", lazy="dynamic"))
    # direction = Column(Float)


class Game(Base):
    __tablename__ = 'game'
    id = Column(Integer, primary_key=True)
    mlbgame_id = Column(String(80), unique=True)
    date = Column(DateTime)
    home_team_id = Column(Integer, ForeignKey("team.id"))
    home_team = relationship("Team", backref=backref("hgames", lazy="dynamic"), foreign_keys=[home_team_id])
    away_team_id = Column(Integer, ForeignKey("team.id"))
    away_team = relationship("Team", backref=backref("agames", lazy="dynamic"), foreign_keys=[away_team_id])
    weather_pop = Column(Integer)
    weather_wind_speed = Column(Float)
    weather_relative_dir = Column(Float)
    weather_temp = Column(Float)
    weather_humid = Column(Float)
    stadium_id = Column(Integer, ForeignKey("stadium.id"))
    stadium = relationship('Stadium')


class BatterStatLine(Base):
    __tablename__ = 'batterstatline'
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('player.id'))
    player = relationship('Player', backref='batterstatlines')
    game_id = Column(Integer, ForeignKey('game.id'))
    game = relationship('Game', backref='batterstatlines')

    avg = Column(Float)
    bb = Column(Integer)
    twob = Column(Integer)
    h = Column(Integer)
    hbp = Column(Integer)
    hr = Column(Integer)
    r = Column(Integer)
    rbi = Column(Integer)
    sb = Column(Integer)
    so = Column(Integer)
    threeb = Column(Integer)
    ab = Column(Integer)
    fd_fpts = Column(Float)

    salary = Column(Integer)

class PitcherStatLine(Base):
    __tablename__ = 'pitcherstatline'
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('player.id'))
    player = relationship('Player', backref='pitcherstatlines')
    game_id = Column(Integer, ForeignKey('game.id'))
    game = relationship('Game', backref='pitcherstatlines')

    era = Column(Float)
    win = Column(Boolean)
    er = Column(Integer)
    so = Column(Integer)
    out = Column(Integer)
    fd_fpts = Column(Float)

    salary = Column(Integer)

class Model(Base):
    '''
    Model table that stores instructions/parameters
    defining a unique machine learning predictor.
    '''
    __tablename__ = 'model'
    id = Column(Integer, primary_key=True)
    predictor_name = Column(String(80))

    hypers = Column(PickleType)
    data_transforms = Column(PickleType)
    data_cols = Column(PickleType)

    nickname = Column(String(80), unique=True)


class PlayerModel(Base):
    '''
    PlayerModel table that stores the concrete
    sklearn predictor object, along with the information
    about the unique player whose data the predictor was trained on.
    '''
    __tablename__ = 'playermodel'
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('player.id'))
    player = relationship('Player', backref='playermodels')
    predictorObj = Column(PickleType)
    model_id = Column(Integer, ForeignKey('model.id'))
    model = relationship('Model', backref='playermodels')

    start_date = Column(DateTime)
    end_date = Column(DateTime)


class Pred(Base):
    '''
    Pred table that stores a dataframe of predictions for a given
    player based on a specified model.
    '''
    __tablename__ = 'pred'
    id = Column(Integer, primary_key=True)
    # players = association_proxy('player_models', 'player')
    # model_id = Column(Integer, ForeignKey('model.id'))
    player_model_id = Column(Integer, ForeignKey('playermodel.id'))
    player_model = relationship('PlayerModel', backref='preds')

    frequency = Column(Integer)
    #start_date = Column(DateTime)
    #end_date = Column(DateTime)

    pred_col = Column(PickleType)
    # hyper_id   = Column(Integer, ForeignKey('modelhyper.id'))

class Roster(Base):
    '''
    Roster table which stores optimal rosters based calculated
    based on date and other parameters.
    '''
    __tablename__ = 'roster'
    id = Column(Integer, primary_key=True)
    date = Column(DateTime)
    #players = relationship("Player", backref="roster")
    rank = Column(Integer)
