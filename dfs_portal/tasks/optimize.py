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
from dfs_portal.schema.mlb import optimize_task_schema
from dfs_portal.models.redis import T_OPTIMIZE

from dfs_portal.core import abstract_predictor as abs_p
from dfs_portal.core.dbutils import get_player_career_start_end, retrain_start_end_cycles, query_player_stat_line, player_stat_line_query2df

from dfs_portal.core import transforms


LOG = getLogger(__name__)
#THROTTLE = 1 * 60 * 60
THROTTLE = 10
SLEEP_FOR = 0.1  # Seconds to wait in between checks.
WAIT_UP_TO = 2  # Wait up to these many seconds for task to finish. Won't block view for more than this.



@celery.task(bind=False, soft_time_limit=120 *60)
def optimize_rosters_task(formData):
    '''
    Generates rosters based on a given date
    '''
    lock = redis.lock(T_OPTIMIZE, timeout=int(THROTTLE))
    have_lock = lock.acquire(blocking=False)
    if not have_lock:
        LOG.warning('{} lock currently active.'.format(T_CREATE_MODEL))
        resObj, err = celery_result_schema.load(
                dict(name='optimize_rosters_task',
                     data=None,
                     status='locked',
                     msg='',
                     currentProgress=0,
                     totalProgress=1,
                )
            )
        return resObj

    rdb.set_trace()
    formData, errors = optimize_task_schema.load(formData)
    if errors:
        resObj, err = celery_result_schema.load(
                dict(name='optimize_rosters_task',
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
