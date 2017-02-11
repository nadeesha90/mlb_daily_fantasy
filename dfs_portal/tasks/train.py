import pudb
import pickle
import argparse
import collections
import os
import sys
import re
import namedtupled
from copy import deepcopy
from pprint import pprint
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

from logging import getLogger
from celery import group
from celery.contrib import rdb
from xmlrpc.client import ServerProxy

from flask.ext.celery import single_instance
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound

from dfs_portal.extensions import celery, db, redis
from dfs_portal.schema.core import celery_result_schema
from dfs_portal.utils.ctools import wait_for_task
from dfs_portal.models.mlb import PlayerModel, Model, Player, BatterStatLine, PitcherStatLine, Game, Pred
from dfs_portal.schema.mlb import player_model_schema, model_schema, pred_schema
from dfs_portal.models.redis import T_CREATE_MODEL, T_FIT_ALL, T_FIT_ID, T_PREDICT_ALL, T_PREDICT_ID

from dfs_portal.config import HardCoded

from dfs_portal.core import abstract_predictor as abs_p
from dfs_portal.core.dbutils import get_player_career_start_end, retrain_start_end_cycles, query_player_stat_line, player_stat_line_query2df, repredict_start_end_cycles

from dfs_portal.core import transforms


LOG = getLogger(__name__)
#THROTTLE = 1 * 60 * 60
THROTTLE = 10
SLEEP_FOR = 0.1  # Seconds to wait in between checks.
WAIT_UP_TO = 2  # Wait up to these many seconds for task to finish. Won't block view for more than this.


######################################
##### Database related functions #####
######################################
# Moved them all to dbutils.py
# So we only have tasks here.
def apply_transforms(df, parameters):
    transformFuncs = parameters.data_transforms
    transformFuncs = [eval('transforms.' + func) for func in transformFuncs]
    transformFuncs = [partial(func, parameters) for func in transformFuncs]
    df = pipe (df, *transformFuncs)
    return df






@celery.task(bind=False, soft_time_limit=120 *60)
def create_model_task(formData):
    '''
    Takes model hypers/transforms, name, data cols and generates a model reference entry.
    '''
    lock = redis.lock(T_CREATE_MODEL, timeout=int(THROTTLE))
    have_lock = lock.acquire(blocking=False)
    if not have_lock:
        LOG.warning('{} lock currently active.'.format(T_CREATE_MODEL))

        resObj, err = celery_result_schema.load(
                dict(name='create_model_task',
                     data=None,
                     status='locked',
                     msg='',
                     currentProgress=0,
                     totalProgress=1,
                )
            )
        return resObj

    # TODO: nickname should be its own separate field.
    formData['nickname'] = formData['hypers']['nickname']
    formData['data_transforms'] = formData['hypers']['data_transforms']

    formData, errors = model_schema.load(formData)
    if errors:
        resObj, err = celery_result_schema.load(
                dict(name='create_model_task',
                     data=formData,
                     status='fail',
                     msg=errors,
                     currentProgress=0,
                     totalProgress=1,
                )
            )
        return resObj

    #modelData = formData.get('model')
    try:
        model = Model.query \
                .filter(Model.predictor_name == formData['predictor_name'])\
                .filter(Model.hypers == formData['hypers'])\
                .filter(Model.data_transforms == formData['data_transforms'])\
                .filter(Model.data_cols == formData['data_cols'])\
                .one()
        LOG.info('A model with these features exists. Use nickname {}'.format(model.nickname))
        resObj, err = celery_result_schema.load(
                dict(name='create_model_task',
                     data=model.nickname,
                     status='fail',
                     msg='Model already exists. Check nickname',
                     currentProgress=0,
                     totalProgress=1,
                )
            )
        return resObj

    except NoResultFound:
        LOG.info('No model found, creating model.')
        formData.pop('hypers_dict')
        formData.pop('data_cols_dict')
        model = Model(**formData)
        db.session.add(model)
        db.session.commit()
        resObj, err = celery_result_schema.load(
                dict(name='create_model_task',
                     data=None,
                     status='success',
                     msg='Create model',
                     currentProgress=0,
                     totalProgress=1,
                )
            )
        return resObj

    except MultipleResultsFound:
        resObj, err = celery_result_schema.load(
                dict(name='create_model_task',
                     data=None,
                     status='fail',
                     msg='Found duplicate Models in the database.',
                     currentProgress=0,
                     totalProgress=1,
                )
            )
        return resObj

@celery.task(bind=False, soft_time_limit=120 *60)
#@single_instance
def fit_all_task(formData):
    '''
    Takes model ref and dates and fits all players to the specifications.
    '''
    lock = redis.lock(T_FIT_ALL, timeout=int(THROTTLE))
    have_lock = lock.acquire(blocking=False)
    if not have_lock:
        LOG.warning('{} lock currently active.'.format(T_FIT_ALL))
        resObj, err = celery_result_schema.load(
                dict(name='fit_all_task',
                     data=None,
                     status='locked',
                     msg='',
                     currentProgress=0,
                     totalProgress=1,
                )
            )
        return resObj


    allPlayers = Player.query\
            .with_entities(Player.id)\
            .filter(Player.player_type == formData['player_type'])\
            .all()
    allForms = []
    for player in allPlayers:
        tempDict = deepcopy(formData)
        tempDict.update(player_id = player[0])
        allForms.append(tempDict)
    fit_all_players = group(fit_player_task.s(form) for form in allForms)
    tasks = fit_all_players.apply_async()
    results = wait_for_task(tasks, WAIT_UP_TO, SLEEP_FOR)
    return results



@celery.task(bind=False, soft_time_limit=120 * 60)
#@single_instance
def fit_player_task(formData):
    '''
    Takes model ref, player, and dates and fits that player to the specifications.
    Can be called directly, or from fit_all_task()
    '''
    lockName = T_FIT_ID.format(formData['player_id'])
    lock = redis.lock(lockName, timeout=int(THROTTLE))
    have_lock = lock.acquire(blocking=False)
    if not have_lock:
        LOG.warning('{} lock currently active.'.format(lockName))
        resObj, err = celery_result_schema.load(
                dict(name='fit_player_task',
                     data=None,
                     status='locked',
                     msg='',
                     currentProgress=0,
                     totalProgress=1,
                )
            )
        return resObj

    try:
        player = Player.query.get(formData['player_id'])
    except IntegrityError:
        resObj, err = celery_result_schema.load(
                dict(name='fit_player_task',
                     data=None,
                     status='fail',
                     msg='Player could not be found',
                     currentProgress=0,
                     totalProgress=1,
                )
            )
        return resObj
    if player is None:
        resObj, err = celery_result_schema.load(
                dict(name='fit_player_task',
                     data=None,
                     status='fail',
                     msg='No player found with given id',
                     currentProgress=0,
                     totalProgress=1,
                )
            )
        return resObj
    try:
        model = Model.query.filter(Model.nickname == formData['model_nickname']).one()
    except NoResultFound:
        resObj, err = celery_result_schema.load(
                dict(name='fit_player_task',
                     data=None,
                     status='fail',
                     msg='No model found with the given nickname.',
                     currentProgress=0,
                     totalProgress=1,
                )
            )
        return resObj
    modelData, errors = model_schema.dump(model)
    
    # If frequency is given, then ignore given start and end dates and just follow through career.
    # If frequency = -1, then use the given start and end dates.
    if formData['frequency'] > 0:
        formData['start_date'], formData['end_date'] = get_player_career_start_end(player.player_type, player.id)
        allEndDates = retrain_start_end_cycles(formData['start_date'], formData['end_date'], formData['frequency'])
    else:
        allEndDates = [ formData['end_date'] ]

    for date in allEndDates:
        formData['end_date'] = date
        try:
            #rdb.set_trace()
            playerModel = PlayerModel.query \
                    .filter(PlayerModel.player_id == player.id)\
                    .filter(PlayerModel.model_id == model.id)\
                    .filter(PlayerModel.start_date == formData['start_date'].replace(hour=0, minute=0))\
                    .filter(PlayerModel.end_date == formData['end_date'].replace(hour=0, minute=0))\
                    .one()
            LOG.info('Using existing model.')

        except NoResultFound:
            LOG.warning('No model found, creating one.')

            predictorObj = abs_p.get_predictor_obj(modelData['predictor_name'], hypers=modelData['hypers'])
            query = query_player_stat_line((player.id, formData['player_type'], formData['start_date'], formData['end_date']))
            df = pd.read_sql(query.statement, query.session.bind)

            df = apply_transforms(df, d2nt(modelData))
            if len(df) < formData['frequency'] * HardCoded.MIN_NUMBER_OF_GAMEDAYS:
                LOG.debug('Not enough game data to bother with building a model.')
                continue

            fitSuccess = predictorObj.fit(df, modelData['data_cols']['features'], modelData['data_cols']['target_col'], validationSplit=modelData['hypers']['validation_split'])



            if fitSuccess:
                playerModelData = {'player': {'id': player.id},
                        'model': {'id': model.id},
                        'start_date': formData['start_date'].strftime('%m/%d/%Y'),
                        'end_date': formData['end_date'].strftime('%m/%d/%Y')}
                playerModelData, errors = player_model_schema.load(playerModelData)
                if errors:
                    resObj, err = celery_result_schema.load(
                        dict(name='fit_player_task',
                             data=playerModelData,
                             status='fail',
                             msg=errors,
                             currentProgress=0,
                             totalProgress=1,
                        )
                    )
                    return resObj
                playerModelData['predictorObj'] = predictorObj
                playerModelData['model'] = model
                playerModelData['player'] = player
                playerModel = PlayerModel(**playerModelData)
                db.session.add(playerModel)
                db.session.commit()



        except MultipleResultsFound:
            resObj, err = celery_result_schema.load(
                        dict(name='fit_player_task',
                             data=None,
                             status='fail',
                             msg='Found duplicate Models in the database.',
                             currentProgress=0,
                             totalProgress=1,
                        )
                    )
            return resObj

    #tas = predict_player_task.delay(formData)
    #res = wait_for_task(tas, WAIT_UP_TO, SLEEP_FOR)
    resObj, err = celery_result_schema.load(
                dict(name='fit_player_task',
                     data=None,
                     status='success',
                     msg=None,
                     currentProgress=1,
                     totalProgress=1,
                )
            )
    return resObj









@celery.task(bind=False, soft_time_limit=120 *60)
#@single_instance
def predict_all_task(formData):
    '''
    Takes model ref and dates and predicts all players to the specifications.
    '''
    lock = redis.lock(T_PREDICT_ALL, timeout=int(THROTTLE))
    have_lock = lock.acquire(blocking=False)
    if not have_lock:
        LOG.warning('{} lock currently active.'.format(T_PREDICT_ALL))
        resObj, err = celery_result_schema.load(
                    dict(name='predict_all_task',
                         data=None,
                         status='locked',
                         msg='',
                         currentProgress=0,
                         totalProgress=1,
                    )
                )
        return resObj


    allPlayers = Player.query\
            .with_entities(Player.id)\
            .filter(Player.player_type == formData['player_type'])\
            .all()
    allForms = []
    for player in allPlayers:
        tempDict = deepcopy(formData)
        tempDict.update(player_id = player[0])
        allForms.append(tempDict)
    predict_all_players = group(predict_player_task.s(form) for form in allForms)
    tasks = predict_all_players.apply_async()
    results = wait_for_task(tasks, WAIT_UP_TO, SLEEP_FOR)
    return results


@celery.task(bind=False, soft_time_limit=120 * 60)
#@single_instance
def predict_player_task(formData):
    lockName = T_PREDICT_ID.format(formData['player_id'])
    lock = redis.lock(lockName, timeout=int(THROTTLE))
    have_lock = lock.acquire(blocking=False)
    if not have_lock:
        LOG.warning('{} lock currently active.'.format(lockName))
        resObj, err = celery_result_schema.load(
                    dict(name='predict_player_task',
                         data=None,
                         status='locked',
                         msg='',
                         currentProgress=0,
                         totalProgress=1,
                    )
                )
        return resObj
    #formData, errors = pred_schema.load(formData)
    #if errors:
    #    return cResult(result=dict(message=errors, data=formData), status=cStatus.fail)

    try:
        player = Player.query.get(formData['player_id'])
    except IntegrityError:
        resObj, err = celery_result_schema.load(
                dict(name='predict_player_task',
                     data=None,
                     status='fail',
                     msg='Player could not be found',
                     currentProgress=0,
                     totalProgress=1,
                )
            )
        return resObj
    if player is None:
        resObj, err = celery_result_schema.load(
                dict(name='predict_player_task',
                     data=None,
                     status='fail',
                     msg='No player found with given id',
                     currentProgress=0,
                     totalProgress=1,
                )
            )
        return resObj

    try:
        model = Model.query.filter(Model.nickname == formData['model_nickname']).one()
    except NoResultFound:
        resObj, err = celery_result_schema.load(
                dict(name='predict_player_task',
                     data=None,
                     status='fail',
                     msg='No model found with the given nickname.',
                     currentProgress=0,
                     totalProgress=1,
                )
            )
        return resObj
    modelData, errors = model_schema.dump(model)

    # If frequency is given, then follow career path, build train and predict grids.
    # If no frequency given, then build the largest model (career path) and use given predict grid.
    formData['model_start_date'], formData['model_end_date'] = get_player_career_start_end(player.player_type, player.id)
    if formData['frequency'] > 0:
        allModelEndDates = retrain_start_end_cycles(formData['model_start_date'], formData['model_end_date'], formData['frequency'])
        allPredictStartDates, allPredictEndDates = repredict_start_end_cycles(formData['model_start_date'], formData['model_end_date'], formData['frequency'])
    else:
        allModelEndDates = [ formData['model_end_date'] ]
        allPredictStartDates = [ formData['start_date'] ]
        allPredictEndDates = [ formData['end_date'] ]
    formData['model_start_date'] = formData['model_start_date'].replace(hour=0, minute=0)
    
    nDates = len(allModelEndDates)
    for i in range(nDates):
        formData['model_end_date'] = allModelEndDates[i].replace(hour=0, minute=0)
        formData['start_date'] = allPredictStartDates[i].replace(hour=0, minute=0)
        formData['end_date'] = allPredictEndDates[i].replace(hour=23, minute=59)

        try:
            playerModel = PlayerModel.query \
                    .filter(PlayerModel.player_id == player.id)\
                    .filter(PlayerModel.model_id == model.id)\
                    .filter(PlayerModel.start_date == formData['model_start_date'].replace(hour=0, minute=0))\
                    .filter(PlayerModel.end_date == formData['model_end_date'].replace(hour=0, minute=0))\
                    .one()
            LOG.info('Using existing model.')

            # will run predict here.
            query = query_player_stat_line((player.id, player.player_type, formData['start_date'], formData['end_date']))
            #rdb.set_trace()
            df = player_stat_line_query2df(query)
            if len(df) == 0:
                LOG.warning('This query has no data.')
                continue
            gameDates = df.date
            #df = pd.read_sql(query.statement, query.session.bind)
            df = apply_transforms(df, d2nt(modelData))
            predScores = playerModel.predictorObj.predict(df, modelData['data_cols']['features'], modelData['data_cols']['target_col'])

            # if we couldn't predict (not enough data? predict failed?), then move on
            if predScores is None:
                continue
            
            yPred = pd.DataFrame({'date':gameDates[1:], 'pred':predScores})
            print(yPred)
            
            # first check if the pred row exists
            # then append to it if it exists, otherwise create a new one
            try:
                #rdb.set_trace()
                pred = Pred.query \
                        .filter(Pred.player_model_id == playerModel.id)\
                        .one()
                LOG.info('Appending to existing pred df.')
                sharedPred = pd.merge(pred.pred_col, yPred, how='outer', on='date')
                sharedPred['pred'] = sharedPred.apply(lambda x: x.pred_y if not np.isnan(x.pred_y) else x.pred_x, axis=1)
                sharedPred = sharedPred.drop(['pred_x', 'pred_y'], axis=1)

                pred.pred_col = sharedPred
                print (pred.pred_col)
                db.session.commit()
                # TODO: currently facing issues with prediction columns stored in the tables. 



            except NoResultFound:
                LOG.info('Creating new pred df')
                predData = {'player_model': {'id': playerModel.id},
                        'frequency': formData['frequency'],
                        'pred_col': yPred}
                predData, errors = pred_schema.load(predData)
                if errors:
                    resObj, err = celery_result_schema.load(
                        dict(name='predict_player_task',
                             data=playerModelData,
                             status='fail',
                             msg=errors,
                             currentProgress=0,
                             totalProgress=1,
                        )
                    )
                    return resObj
                predData['player_model'] = playerModel
                predData['pred_col'] = yPred
                pred = Pred(**predData)
                db.session.add(pred)
                db.session.commit()

            except MultipleResultsFound:
                resObj, err = celery_result_schema.load(
                        dict(name='predict_player_task',
                             data=None,
                             status='fail',
                             msg='Found duplicate Preds in the database.',
                             currentProgress=0,
                             totalProgress=1,
                        )
                    )
                return resObj

        except NoResultFound:
            LOG.info('No model found for {}-{}.'\
                    .format(formData['model_start_date'],
                    formData['model_end_date']))
            continue
            #resObj, err = celery_result_schema.load(
            #            dict(name='predict_player_task',
            #                 data=None,
            #                 status='fail',
            #                 msg='No Model found in database.',
            #                 currentProgress=0,
            #                 totalProgress=1,
            #            )
            #        )
            #return resObj
        except MultipleResultsFound:
            resObj, err = celery_result_schema.load(
                        dict(name='predict_player_task',
                             data=None,
                             status='fail',
                             msg='Found duplicate Models in the database.',
                             currentProgress=0,
                             totalProgress=1,
                        )
                    )
            return resObj
    resObj, err = celery_result_schema.load(
                dict(name='predict_player_task',
                     data=None,
                     status='success',
                     msg=None,
                     currentProgress=1,
                     totalProgress=1,
                )
            )
    return resObj


