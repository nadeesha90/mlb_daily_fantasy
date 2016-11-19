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
from dfs_portal.utils.ctools import wait_for_task, cResult, cStatus
from dfs_portal.models.mlb import Model, Player, BatterStatLine, PitcherStatLine, Game, Pred
from dfs_portal.schema.mlb import model_schema, model_fitting_function_schema
from dfs_portal.models.redis import T_FIT_ALL, T_FIT_ID, T_PREDICT_ALL, T_PREDICT_ID

from dfs_portal.config import HardCoded

from dfs_portal.core import abstract_predictor as abs_p
from dfs_portal.core.dbutils import get_player_career_start_end

from dfs_portal.core import transforms


LOG = getLogger(__name__)
#THROTTLE = 1 * 60 * 60
THROTTLE = 10
SLEEP_FOR = 0.1  # Seconds to wait in between checks.
WAIT_UP_TO = 2  # Wait up to these many seconds for task to finish. Won't block view for more than this.


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
    #playerTup = (playerId, playerType, startDate, endDate)
    playerId, playerType, startDate, endDate = playerTup 
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
def fit_all_task(formData):

    lock = redis.lock(T_FIT_ALL, timeout=int(THROTTLE))
    have_lock = lock.acquire(blocking=False)
    if not have_lock:
        LOG.warning('{} lock currently active.'.format(T_FIT_ALL))
        return cResult(result=None, status=cStatus.locked)


    allPlayers = Player.query\
            .with_entities(Player.id)\
            .filter(Player.player_type == formData['player_type'])\
            .all()
    allForms = []
    for player in allPlayers:
        tempDict = deepcopy(formData)
        tempDict.update(player_id = player[0])
        allForms.append(tempDict)
    #rdb.set_trace()
    fit_all_players = group(fit_player_task.s(form) for form in allForms)
    tasks = fit_all_players.apply_async()
    results = wait_for_task(tasks, WAIT_UP_TO, SLEEP_FOR)
    return results

@celery.task(bind=False, soft_time_limit=120 * 60)
#@single_instance
def fit_player_task(formData):
    
    lockName = T_FIT_ID.format(formData['player_id'])
    lock = redis.lock(lockName, timeout=int(THROTTLE))
    have_lock = lock.acquire(blocking=False)
    if not have_lock:
        LOG.warning('{} lock currently active.'.format(lockName))
        return cResult(result=dict(message='Celery task is locked.', data=None), status=cStatus.locked)
    
    formData, errors = model_fitting_function_schema.load(formData)
    if errors:
        return cResult(result=dict(message=errors, data=formData), status=cStatus.fail)

    try:
        player = Player.query.get(formData['player_id'])
    except IntegrityError:
        return cResult(result=dict(message='Player could not be found.', data=None), status=cStatus.fail)
    if player is None:
        return cResult(result=dict(message='No player found with given id', data=None), status=cStatus.fail)

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
        LOG.info('Using existing model')
    except NoResultFound:
        LOG.warning('No model found, creating one.')
        # need to store listified versions of dicts in db, but want to use dicts in logic
        # storing lists in temporary variables, will refill after logic and before storing in db
        hypersList = modelData['hypers']
        data_colsList = modelData['data_cols']
        
        modelData['hypers'] = modelData.pop('hypers_dict')
        modelData['data_cols'] = modelData.pop('data_cols_dict')

        modelObj = abs_p.get_predictor_obj(modelData['predictor_name'], hypers=modelData['hypers'])
        query = query_player_stat_line((player.id, formData['player_type'], modelData['start_date'], modelData['end_date']))
        df = pd.read_sql(query.statement, query.session.bind)

        df = apply_transforms(df, d2nt(modelData))
        fitSuccess = modelObj.fit(df, modelData['data_cols']['features'], modelData['data_cols']['target_col'], validationSplit=modelData['hypers']['validation_split'])
        
        # storing listified versions back into model object before submitting to db
        modelData['hypers'] = hypersList
        modelData['data_cols'] = data_colsList
        if fitSuccess:
            modelData['player'] = player
            modelData['modelObj'] = modelObj
            model = Model(**modelData)
            db.session.add(model)
            db.session.commit()

    except MultipleResultsFound:
        return cResult(result=dict(message='Found duplicate Models in the database.', data=None), status=cStatus.fail)

    return cResult(result='fitp', status=cStatus.success)





@celery.task(bind=False, soft_time_limit=120 * 60)
#@single_instance
def predict_player_task(formData):
    
    lockName = T_PREDICT_ID.format(formData['player_id'])
    lock = redis.lock(lockName, timeout=int(THROTTLE))
    have_lock = lock.acquire(blocking=False)
    if not have_lock:
        LOG.warning('{} lock currently active.'.format(lockName))
        return cResult(result=dict(message='Celery task is locked.', data=None), status=cStatus.locked)
    
    formData, errors = model_predict_function_schema.load(formData)
    if errors:
        return cResult(result=dict(message=errors, data=formData), status=cStatus.fail)

    try:
        player = Player.query.get(formData['player_id'])
    except IntegrityError:
        return cResult(result=dict(message='Player could not be found.', data=None), status=cStatus.fail)
    if player is None:
        return cResult(result=dict(message='No player found with given id', data=None), status=cStatus.fail)

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
        LOG.info('Using existing model')
        # need to store listified versions of dicts in db, but want to use dicts in logic
        # storing lists in temporary variables, will refill after logic and before storing in db
        hypersList = modelData['hypers']
        data_colsList = modelData['data_cols']
        
        modelData['hypers'] = modelData.pop('hypers_dict')
        modelData['data_cols'] = modelData.pop('data_cols_dict')

        modelObj = abs_p.get_predictor_obj(modelData['predictor_name'], hypers=modelData['hypers'])
        query = query_player_stat_line((player.id, formData['player_type'], modelData['pred_start_date'], modelData['pred_end_date']))
        df = pd.read_sql(query.statement, query.session.bind)

        df = apply_transforms(df, d2nt(modelData))
        predCol = modelObj.predict(df, modelData['data_cols']['features'], modelData['data_cols']['target_col'])
        
        rdb.set_trace()
        pred = Pred(**modelData)
        db.session.commit()

    except NoResultFound:
        return cResult(result=dict(message='Did not find the Model in the database.', data=None), status=cStatus.fail)
    except MultipleResultsFound:
        return cResult(result=dict(message='Found duplicate Models in the database.', data=None), status=cStatus.fail)
    return cResult(result='fitp', status=cStatus.success)


