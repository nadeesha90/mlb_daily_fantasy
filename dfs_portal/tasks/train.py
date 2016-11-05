import argparse
import collections
import os
import sys
import re
import namedtupled
from copy import deepcopy
from pprint import pprint as print
from calendar import Calendar
from datetime import datetime 
#Pypi modules
import yaml
from bs4 import BeautifulSoup
import mlbgame
import numpy as np
import pandas as pd
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

from dfs_portal.utils.htools import hprogress, flatten, merge_fuzzy, cached_read_html_page, hjrequest, d2nt, isempty, dget, lmap, reset_to_start_of_week


import pudb
import pickle

from distutils.version import LooseVersion
from logging import getLogger
from celery import group
from celery.contrib import rdb
from xmlrpc.client import ServerProxy

from flask.ext.celery import single_instance
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound

from dfs_portal.extensions import celery, db, redis
from dfs_portal.models.mlb import Model, Player, BatterStatLine, PitcherStatLine, Game
from dfs_portal.schema.mlb import model_schema, model_fitting_function_schema
from dfs_portal.models.redis import POLL_SIMPLE_THROTTLE, TOTAL_PROGRESS, CURRENT_PROGRESS

from dfs_portal.config import HardCoded

from dfs_portal.core import abstract_predictor as abs_p
from dfs_portal.core.dbutils import get_player_career_start_end

from dfs_portal.core import transforms


LOG = getLogger(__name__)
#THROTTLE = 1 * 60 * 60
THROTTLE = 10


######################################
##### Database related functions #####
######################################
def apply_transforms(df, parameters):
    transformFuncs = parameters.data_transforms
    transformFuncs = [eval('transforms.' + func) for func in transformFuncs]
    transformFuncs = [partial(func, parameters) for func in transformFuncs]
    df = pipe (df, *transformFuncs)
    return df

def query_player_stat_line(playerTup):
    # playerTup = (playerId, playerType, startDate, endDate)
    if playerType == 'batter':
        query = BatterStatLine.query\
                .join(Game)\
                .filter(BatterStatLine.player_id == playerId)\
                .filter(
                        Game.date >= startDate,
                        Game.date < endDate)
    else:
        query = PitcherStatLine.query\
                .join(Game)\
                .filter(PitcherStatLine.player_id == playerId)\
                .filter(
                        Game.date >= startDate,
                        Game.date < endDate)
    return query


@celery.task(bind=False, soft_time_limit=120 *60)
#@single_instance
def fit_task(formData):

    lock = redis.lock(POLL_SIMPLE_THROTTLE, timeout=int(THROTTLE))
    have_lock = lock.acquire(blocking=False)
    if not have_lock:
        LOG.warning('poll_simple() task has already executed in the past 10 seconds. Rate limiting.')
        return None


    if formData['train_select'] == 'all':
        allPlayers = Player.query\
                .with_entities(Player.id)\
                .filter(Player.player_type == formData['player_type'])\
                .all()
        allForms = []
        for player in allPlayers:
            tempDict = deepcopy(formData)
            tempDict.update(player_id = player[0])
            allForms.append(tempDict)
        rdb.set_trace()
        fit_all_players = group(fit_player.s(form) for form in allForms)
        fit_all_players.apply_async()
        #fit_all_players.get()
    else:
        #rdb.set_trace()
        fit_player.delay(formData)



@celery.task(bind=False, soft_time_limit=120 * 60)
#@single_instance
def fit_player(formData):
    
    #lock = redis.lock(POLL_SIMPLE_THROTTLE, timeout=int(THROTTLE))
    #have_lock = lock.acquire(blocking=False)
    #if not have_lock:
    #    LOG.warning('poll_simple() task has already executed in the past 10 seconds. Rate limiting.')
    #    return None
    
    # *** UNCOMMENT AFTERWARDS TO VALIDATE data    
    #formData, errors = model_fitting_function_schema.load(formData)
    #if errors:
    #    return jsonify(message=errors, data=formData), 422

    formData['player_id'] = 1
    try:
        player = Player.query.get(formData['player_id'])
    except IntegrityError:
        return jsonify({'message': 'Player could not be found.'}), 400
    if player is None:
        return jsonify({'message': 'No player found with given id',
                        'data':formData}), 400

    modelData = formData.get('model')
    try:
        model = Model.query \
                .filter(Model.predictor_name == modelData['predictor_name'])\
                .filter(Model.player_id == player.id)\
                .filter(Model.start_date == modelData['start_date'])\
                .filter(Model.end_date == modelData['end_date'])\
                .filter(Model.hypers == modelData['hypers'])\
                .filter(Model.data_transforms == modelData['data_transforms'])\
                .filter(Model.data_cols == modelData['data_cols'])\
                .one()
    except NoResultFound:
        modelData['hypers'] = modelData.pop('hypers_dict')
        modelData['data_cols'] = modelData.pop('data_cols_dict')

        modelObj = abs_p.get_predictor_obj(modelData['predictor_name'], hypers=modelData['hypers'])
        query = query_player_stat_line((player.id, formData['player_type'], modelData['start_date'], modelData['end_date']))
        df = pd.read_sql(query.statement, query.session.bind)

        df = apply_transforms(df, d2nt(modelData))
        fitSuccess = modelObj.fit(df, modelData['data_cols']['features'], modelData['data_cols']['target_col'], validationSplit=modelData['hypers']['validation_split'])
        
        if fitSuccess:
            modelData['player'] = player
            modelData['modelObj'] = modelObj
            model = Model(**modelData)
            db.session.add(model)

    except MultipleResultsFound:
        print ('Found more than one PlayerModel for player and hyper and dates.')
        print ('Aborting...')
        sys.exit(1)

    db.session.commit()
    return
















@celery.task(bind=True, soft_time_limit=120 * 60)
@single_instance
def predict_task(formData):
    lock = redis.lock(POLL_SIMPLE_THROTTLE, timeout=int(THROTTLE))
    have_lock = lock.acquire(blocking=False)
    if not have_lock:
        LOG.warning('poll_simple() task has already executed in the past 10 seconds. Rate limiting.')
        return None
    
    # *** UNCOMMENT AFTERWARDS TO VALIDATE data    
    #formData, errors = model_fitting_function_schema.load(formData)
    #if errors:
    #    return jsonify(message=errors, data=jsonData), 422
    
    try:
        player = Player.query.get(1)
    except IntegrityError:
        return jsonify({'message': 'Player could not be found.'}), 400
    if player is None:
        return jsonify({'message': 'No player found with given id',
                        'data':jsonData}), 400
    
    startDate   = pipe('2016-08-09',
            parse_date,
            reset_to_start_of_week)
    endDate     = parse_date('2016-08-16')
    pStartDate  = parse_date('2016-09-01')
    pEndDate    = parse_date('2016-09-02')
    formData = {
        'ptype': 'batter',
        'player_id': player.id,
        'model': {
            'start_date': startDate,
            'end_date': endDate,
            'name': 'lasso',
            'hypers': {'verbose': True, 'ewma_enabled': False, 'days_to_average': 10, 'shift_by_days': 1},
            'data_transforms': ['ewma', 'shift'],
        },
        'features': {
            'unknowns':['avg', 'bb', 'twob', 'h', 'hbp', 'hr', 'r', 'rbi', 'sb', 'so', 'threeb', 'ab'],
            'knowns':[],
        },
        'predict_start_date': pStartDate,
        'predict_end_date': pEndDate,
        'target_col': 'fd_fpts',
    }
    playerType = formData['ptype']
    modelData = formData['model']


    try:
        model = Model.query \
                .filter(Model.name == modelData['name'])\
                .filter(Model.player_id == player.id)\
                .filter(Model.start_date == modelData['start_date'])\
                .filter(Model.end_date == modelData['end_date'])\
                .filter(Model.hypers == modelData['hypers'])\
                .filter(Model.data_transforms == modelData['data_transforms'])\
                .one()
    
    except NoResultFound:
        print ('No PlayerModel found for player, hyper, and dates.')
        print ('Aborting...')
        sys.exit(1)

    except MultipleResultsFound:
        print ('Found more than one PlayerModel for player and hyper and dates.')
        print ('Aborting...')
        sys.exit(1)
    
    query = query_player_stat_line(player.id, playerType, modelData['start_date'], modelData['end_date'])
    df = pd.read_sql(query.statement, query.session.bind)
    df = apply_transforms(df, formData)
    df = model.predict(df, formData['features'], formData['target_col'])
    return df





# fetch_and_add_stat_lines_to_db(startDate, endDate)

