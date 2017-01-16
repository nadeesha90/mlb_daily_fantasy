import argparse
import collections
import os
import sys
import re
from pprint import pprint
from calendar import Calendar
from datetime import datetime
#Pypi modules
import yaml
from bs4 import BeautifulSoup
import mlbgame
import numpy as np
import pudb
from flask import Flask, jsonify
from toolz import compose, partial, valmap, pipe, merge
from toolz import dicttoolz
#from toolz.curried import map, filter
from dateutil.parser import parse as parse_date

from monad.decorators import maybe
from monad.types.maybe import Nothing, Just
from monad.actions import tryout
#from maybe import *

from dfs_portal.utils.htools import hprogress, flatten, merge_fuzzy, cached_read_html_page, hjrequest, d2nt, isempty, dget, lmap

import pudb
import pickle

from distutils.version import LooseVersion
from logging import getLogger
from celery.contrib import rdb
from xmlrpc.client import ServerProxy

from flask.ext.celery import single_instance

from dfs_portal.extensions import celery, db, redis
from dfs_portal.models.mlb import *
from dfs_portal.schema.mlb import *
from dfs_portal.models.redis import T_SYNC_PLAYERS
from dfs_portal.utils.ctools import wait_for_task
from dfs_portal.models.core import CeleryResult
from dfs_portal.schema.core import celery_result_schema


from dfs_portal.config import HardCoded

LOG = getLogger(__name__)
#THROTTLE = 1 * 60 * 60
THROTTLE = 10


######################################
##### Database related functions #####
######################################
def get_one(Table, data):
    try:
        result = Table.query.filter_by(**data).one() # Raises error on more than one found.
    except NoResultFound:
        print ('Could not find any...{}'.format(data))
        print('Aborting...')
        sys.exit(1)
    except MultipleResultsFound:
        print ('Found more than one in get_one.')
        print('Aborting...')
        sys.exit(1)

    return result
def get_one_or_add(Table, queryData, insertData=None):
    if insertData is None:
        insertData = queryData
    try:
        result = Table.query.filter_by(**queryData).one() # Raises error on more than one found.
    except NoResultFound:
        result = Table (**insertData)
        db.session.add(result)
        db.session.commit()

    except MultipleResultsFound:
        print ('Found more than one in get_one_or_add.')
        print('Aborting...')
        sys.exit(1)

    return result
def sql2df(query):
    result = pd.read_sql(query.statement, query.session.bind)
    resultm = result.values # convert to np matrix
    cols   = list(result.columns)
    result = dumps({'arr':resultm, 'columns': cols})
    return result
def update_statline(StatlineClass, player, date, datePlusThresh, salary):
    success = True
    try:
        psl = StatlineClass.query \
                .join(Game)\
                .filter(StatlineClass.player_id == player.id)\
                .filter(
                    Game.date >= date,
                    Game.date < datePlusThresh)\
                .one()
        if psl.salary is None:
            psl.salary = salary
            db.session.add(psl)
            db.session.commit()

    except NoResultFound:
        print ('No statline found for player: {}, date: {}'\
                .format(player.full_name, date))
        # The player might be marked as Pitcher accidentally,
        # switch to batter and try again
        success = False
    except MultipleResultsFound:
        print ('Multiple statline found for player: {} - {}, date: {}'\
                .format(player.full_name, player.player_type, date))
        print('Aborting...')
        sys.exit(1)
    return success
def get_player_by_name(playerType, fullName, team):
    lastName = fullName.split(' ')[1]
    lastNameToked = '%{}%'.format(lastName).lower()

    ############### Algorithm #####################
    # 1. Try matching with toked last name for that specific team.
    #   2a. If no matches found, try fuzzy matching with full name.
    #       #2ai. If no matches found, abort.
    #   2b. If multiple matches found, try fuzzy matching with full name.
    #       #2bi. If no matches found, abort.

    # Get player info
    try:
        player = Player.query\
                .filter(Player.last_name.like(lastNameToked))\
                .filter(Player.player_type == playerType)\
                .filter(Player.teams.any(name=team.name))\
                .one()
    except (MultipleResultsFound, NoResultFound):
        print ('Attempting fuzzy string matching')
        allPlayerFullNamesInTeam = Player.query\
                .filter(Player.teams.any(name=team.name))\
                .all()
        allPlayerFullNamesInTeam = map(lambda x: x.full_name, allPlayerFullNamesInTeam)
        closestList = difflib.get_close_matches(fullName, allPlayerFullNamesInTeam, n=1, cutoff=0.7)
        if not closestList:
               print('Could not find any similar name to {}'.format(fullName))
               print('Aborting...')
               sys.exit(1)
        closest = closestList[0]
        try:
            player = Player.query\
                    .filter(Player.full_name == closest) \
                    .filter(Player.player_type == playerType)\
                    .filter(Player.teams.any(name=team.name))\
                    .one()

            playerType = player.player_type

        except (MultipleResultsFound, NoResultFound):
            print(traceback.format_exc())
            print('Aborting...')
            sys.exit(1)

    return player, playerType


def update_package_list():
    """
    Gets game info from mlbgame
    """
    pass

    #for name, data in packages.items():
        #db.session.add(Package(name=name, summary=data['summary'], latest_version=data['version']))
    #db.session.commit()
    #return list(new_package_names)
def add_stat_line_to_db(jsonData):
    if not jsonData:
        return 'No input data provided', jsonData, 400

    dateStr = str(jsonData['game_date'])
    dateObj = jsonData['game_date']
    # Add hteam
    teamData = {
                'name':jsonData['hteam'],
                'cityAbbr':HardCoded.team_map_retro[jsonData['hteam']],
                'city':HardCoded.team_to_city[jsonData['hteam']],
               }
    teamData, errors = team_schema.load(teamData)
    if errors:
        return errors, teamData, 422
    # noinspection PyTypeChecker
    hteam = get_one_or_add(Team, teamData)
    # Add ateam
    # if team does not exist in map, then error out
    # because its some shit like seminoles or eagles
    ateamName = jsonData['ateam']

    cityAbbr = HardCoded.team_map_retro.get(jsonData['ateam'])
    if not cityAbbr:
        return 'Team not found...', ateamName, 423
    teamData = {
                'name': ateamName,
                'cityAbbr':cityAbbr,
                'city':HardCoded.team_to_city[jsonData['ateam']],
               }
    teamData, errors = team_schema.load(teamData)
    if errors:
        return errors, teamData, 422
    ateam = get_one_or_add(Team, teamData)

    # Add stadium
    stadiumName = jsonData.get('stadium')
    if stadiumName is not None:
        stadiumData = {'name':stadiumName, 'team':team_schema.dump(hteam).data}
        stadiumDataCleaned, errors = stadium_schema.load(stadiumData)
        if errors:
            return errors, stadiumDataCleaned, 422
        stadiumDataCleaned['team'] = hteam
        stadium = get_one_or_add(Stadium, stadiumDataCleaned)

    # Add game
    gameData = {
                'mlbgame_id':jsonData['mlbgame_game_id'],
                'date':dateStr,
                'home_team':team_schema.dump(hteam).data,
                'away_team':team_schema.dump(ateam).data,
                }
    gameDataClean, errors = game_schema.load(gameData)
    if errors:
        return errors, gameData, 422
    # Convert schema dict to objects accepted by db
    gameDataClean['home_team'] = hteam
    gameDataClean['away_team'] = ateam
    # noinspection PyTypeChecker
    game = get_one_or_add(Game, gameDataClean)


    playersData = jsonData['all_player_stats']
    for player in playersData:
        # add all batters  and pitchers to db
        team = player['team']
        if team == hteam.name:
            team = hteam
        else:
            team = ateam

        playerDataInsert = {
            'full_name':player['full_name'],
            'last_name':player['last_name'],
            'mlbgame_id':player['mlbgame_player_id'],
            'player_type':player['player_type'],
        }
        playerDataInsert, errors = player_schema.load(playerDataInsert)
        if errors:
            return errors, playerDataInsert, 422
        playerDataQuery = playerDataInsert.copy()
        del playerDataQuery ['last_name']
        _player = get_one_or_add (Player, playerDataQuery, playerDataInsert)
        try:
            _playerTeams = Team.query\
                        .filter(Player.id == _player.id)\
                        .filter(Team.id == team.id)\
                        .one()
        except NoResultFound:
            teamPlayerLink = TeamPlayer(
                                team=team,
                                player=_player,
                                team_join_date=dateObj)
            db.session.add(teamPlayerLink)
            db.session.commit()
        except MultipleResultsFound:
            print ('Found more than one team for player')
            print('Aborting...')
            sys.exit(1)


        # add batters statline
        if player['player_type'] == 'batter':
            statlineData, errors = batter_stat_line_schema.load(player)
            if errors:
                #pprint (player)
                return errors, player, 422
            statlineData['player'] = _player
            statlineData['game'] = game
            # don't add statline if already exists:
            try:
                statline = BatterStatLine.query\
                        .filter(BatterStatLine.player_id == _player.id)\
                        .filter(BatterStatLine.game_id == game.id)\
                        .one()
            except NoResultFound:
                result = BatterStatLine(**statlineData)
                db.session.add(result)
                db.session.commit()
            except MultipleResultsFound:
                print ('Found more than one statline for player and game.')
                print('Aborting...')
                sys.exit(1)
        # add pitcher statline
        elif player['player_type'] == 'pitcher':
            statlineData, errors = pitcher_stat_line_schema.load(player)
            if errors:
                return errors,player, 422
            statlineData['player'] = _player
            statlineData['game'] = game
            # don't add statline if already exists:
            try:
                statline = PitcherStatLine.query\
                        .filter(PitcherStatLine.player_id == _player.id)\
                        .filter(PitcherStatLine.game_id == game.id)\
                        .one()
            except NoResultFound:
                result = PitcherStatLine(**statlineData)
                db.session.add(result)
                db.session.commit()
            except MultipleResultsFound:
                print ('Found more than one statline for player and game')
                print('Aborting...')
                sys.exit(1)

    db.session.commit()
    return 'Done!', {}, 200



def add_data_to_db(dataList):
    statuses = lmap(add_stat_line_to_db, dataList)
    return statuses

@maybe(nothing_on_exception=(TypeError,IndexError))
def parse_misc_game_data_page(page):
    soup = BeautifulSoup(page, 'lxml')
    fullStr = soup.findAll('h4')[0].text
    matchObj = re.search('^.*\) at (.*)$' , fullStr)
    stadium = matchObj.group(1).strip()
        #if matchObj:
        #else:
            #stadium = Nothing

    return stadium

def fetch_misc_game_data_from_db(hteam):
    team = Team.query.filter_by(name=hteam).first()
    team = Nothing if team is None else Just(team)
    #stadiumName = team >> (lambda x: Just(x.stadium.all()))
    #TODO: temporary
    stadiumName = None
    if stadiumName:
        data = {'stadium': stadiumName}
    else:
        data = Nothing
    return data


@maybe(predicate=lambda res: not isempty(res),
       nothing_on_exception=None)
def fetch_misc_game_data_from_web(date, hteam):
    data = {}
    teamAbbr = HardCoded.team_map_retro[hteam].upper()

    # http://www.retrosheet.org/boxesetc/2011/B03310KCA2011.htm
    url = 'http://www.retrosheet.org/boxesetc/{year}/B{month:02d}{date:02d}0{team}{year}.htm'\
          .format(team=teamAbbr, year=date.year, month=date.month, date=date.day)
    fPath = os.path.join(HardCoded.baseBallRefSaveDir, '{}_{}.html'.format(hteam, date))
    page = cached_read_html_page(url, fPath)
    stadiumName = page >> parse_misc_game_data_page
    makemap = lambda v: dict({'stadium':v})
    data = stadiumName >> makemap
    #if stadiumName:
        #data = {'stadium': stadiumName}
    if data is Nothing:
        data = {}
    return data


#@maybe
def fetch_data_from_retro(date, hteam):
    # First attempt to obtain it from db
    # then fallback to website
    fetch = tryout(
                fetch_misc_game_data_from_db,
                partial(fetch_misc_game_data_from_web, date))
    result = fetch(hteam)
    return result

def calc_fd_fantasy_pts(playerType, playerStats):

    if playerType == "batter":
        fpts = 3*(playerStats['h']-(playerStats['twob']+playerStats['threeb']+playerStats['hr'])) + 6*playerStats['twob'] + 9*playerStats['threeb'] + 12*playerStats['hr'] + 3.5*playerStats['rbi'] + 3.2*playerStats['r'] + 3*playerStats['bb'] + 6*playerStats['sb'] + 3*playerStats['hbp']
    elif playerType == "pitcher":
        fpts =  12*playerStats['win']-3*playerStats['er']+3*playerStats['so']+3*(playerStats['out']/3.0)
    else:
        raise ValueError
    return fpts


def get_player_stats(playerType, team, stats):
    # Gets all the member variables stored in the stats object.
    # and converts them to kv pairs.
    stats = dict(vars(stats))
    # Common stats for batters and pitchers
    stats['full_name'] = stats['name_display_first_last']
    stats['last_name'] = stats['name']
    stats['mlbgame_player_id'] = stats['id']
    stats['team'] = team
    stats['player_type'] = playerType
    filteredStats = ['mlbgame_player_id', 'team', 'full_name', 'last_name', 'player_type', 'fd_fpts']

    if playerType == 'batter':
        stats['twob'] = stats['t']
        stats['threeb'] = stats['d']
        fdPts = calc_fd_fantasy_pts(playerType, stats)
        filteredStats.extend(['avg', 'bb','twob','h','hbp','hr','r','rbi','sb','so','threeb','ab'])
    elif playerType == 'pitcher':
        win = stats.get('win')
        if win is None:
            stats['win'] = 0
        else:
            stats['win'] = 1
        eraFiltered = stats.get('era')
        if isinstance(eraFiltered, str) and '-' in eraFiltered:
            stats['era'] = 0.0
        fdPts = calc_fd_fantasy_pts(playerType, stats)
        filteredStats.extend(['era', 'win', 'er', 'so', 'out'])
    else:
        raise ValueError

    stats['fd_fpts'] = fdPts

    # Make sure we got all the stats we wanted.
    fstats = dicttoolz.keyfilter(lambda k: k in filteredStats, stats)
    assert (len(fstats.keys()) == len(filteredStats)), 'Could not find all specced stats'
    return fstats


@maybe(predicate=lambda res: not isempty(res),
       nothing_on_exception=None)
def fetch_stat_lines_from_mlbgame(date):
    print ('Fetching data for {}'.format(date))
    resultList = []
    gameList = mlbgame.day(date.year, date.month, date.day)
    for game in gameList:
        try:
            stats = mlbgame.player_stats(game.game_id)
        except ValueError:
            continue


        mlbgame_gameid = game.game_id

        game_date = game.date

        hteam = game.home_team.lower()
        ateam = game.away_team.lower()

        allPlayersStats = list(map(partial(get_player_stats, 'batter', hteam), stats['home_batting']))
        allPlayersStats.extend(map(partial(get_player_stats, 'batter', ateam), stats['away_batting']))
        allPlayersStats.extend(map(partial(get_player_stats, 'pitcher', hteam), stats['home_pitching']))
        allPlayersStats.extend(map(partial(get_player_stats, 'pitcher', ateam), stats['away_pitching']))

        data = {'hteam': hteam,
                'ateam': ateam,
                'game_date': game_date,
                'mlbgame_game_id': mlbgame_gameid,
                'all_player_stats': allPlayersStats,
                }
        resultList.append(data)
    return resultList

@maybe(predicate=lambda res: not isempty(res),
       nothing_on_exception=None)
def fetch_all_game_data(date):
    #statLineData = fetch_stat_line_from_mlbgame(date)
    #hteam = dget(statLineData, 'hteam')
    #miscData = hteam >> partial(fetch_data_from_retro, date)
    #gameData =

    #data = merge(
                #fetch_data_from_retro(date),
                #)
    allDatas = []

    statLineDatas = fetch_stat_lines_from_mlbgame(date)

    def fetch_and_merge(statLineData):
        hteam = statLineData.get('hteam')
        miscData = fetch_data_from_retro(date, hteam)
        if miscData is Nothing:
            miscData = Just({})

        safe_merge = lambda s, m: {} if (s is Nothing) else merge(s, m)
        allData = miscData >> partial(safe_merge, statLineData)
        return allData

    #lmap = lambda x, y: list(map(x,y))
    allDatas = statLineDatas >> partial(lmap, fetch_and_merge)
    if allDatas is Nothing:
        allDatas = {}
    return allDatas


@celery.task(bind=True, soft_time_limit=120 * 60)
def fetch_and_add_stat_lines_to_db(self, startDate, endDate):
    startDate = parse_date(startDate)
    endDate = parse_date(endDate)
    total = (endDate - startDate)
    total = total.days
    lock = redis.lock(T_SYNC_PLAYERS, timeout=int(THROTTLE))
    have_lock = lock.acquire(blocking=False)
    if not have_lock:
        LOG.warning('poll_simple() task has already executed in the past 10 seconds. Rate limiting.')
        return None


    cal = Calendar()
    allDates = [cal.yeardatescalendar(2011) +
                cal.yeardatescalendar(2012) +
                cal.yeardatescalendar(2013) +
                cal.yeardatescalendar(2014) +
                cal.yeardatescalendar(2015) +
                cal.yeardatescalendar(2016)
               ]
    allDates = pipe (allDates,
                     flatten,
                     set,
                     list,
                     sorted)
    assert startDate < endDate, 'start_date should be before end_date!'
    allErrors = []
    allDates = list(filter(lambda date: date >= startDate.date() and date < endDate.date(), allDates))
    for i, date in enumerate(allDates):
            #redis.incr(CURRENT_PROGRESS, amount=1)
            #resObj = celery_result_schema.load(result=dict( message='', data=dict(name='fetch_and_add_stat_lines_to_db', current=i,total=len(allDates))), status=cStatus.fail)
            resObj, err = celery_result_schema.load(
                dict(name='fetch_and_add_stat_lines_to_db',
                     data=None,
                     status='locked',
                     msg='Data: {}'.format(date),
                     currentProgress=i,
                     totalProgress=len(allDates),
                )
            )
            self.update_state(state='PROGRESS', meta=resObj)
            statuses = fetch_all_game_data(date) >> add_data_to_db
            errorFound = False

            if statuses:
                for message, data, status in statuses:
                    if status != 200:
                        if status != 423:
                            errorFound = True
                        print ('', status)
                        print ('Message: ')
                        pprint(message)
                        print ('Data: ')
                        pprint(data)
                        allErrors.append((message,data))

            if errorFound:
                resObj, err = celery_result_schema.load(
                    dict(name='fetch_and_add_stat_lines_to_db',
                     data=allErrors,
                     status='fail',
                     msg='Errors found when insert data in db.',
                     currentProgress=i,
                     totalProgress=len(allDates),
                    )
                )
                return resObj

    resObj, err = celery_result_schema.load(
                dict(name='fetch_and_add_stat_lines_to_db',
                     data=None,
                     status='success',
                     msg='Synced all data!',
                     currentProgress=i,
                     totalProgress=len(allDates),
                )
            )
    return resObj
# fetch_and_add_stat_lines_to_db(startDate, endDate)

