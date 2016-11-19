import pudb
import time
import numpy as np
import toolz
from dateutil.parser import parse as parse_date



import yaml
from flask import redirect, render_template, url_for, request, jsonify, session
from datatables import ColumnDT, DataTables
from sqlalchemy.orm import subqueryload, joinedload, contains_eager, immediateload
from sqlalchemy.sql import func

from dfs_portal.blueprints import mlb_dashboard
from dfs_portal.core import flash
from dfs_portal.extensions import redis, db
from dfs_portal.models.mlb import *
from dfs_portal.models.redis import POLL_SIMPLE_THROTTLE
from dfs_portal.tasks.mlbgame import fetch_and_add_stat_lines_to_db
from dfs_portal.tasks.train import fit_task
from dfs_portal.utils.htools import lmap, hredirect
from dfs_portal.core.abstract_predictor import get_available_predictors
from dfs_portal.core.transforms import get_available_transforms
SLEEP_FOR = 0.1  # Seconds to wait in between checks.
WAIT_UP_TO = 5  # Wait up to these many seconds for task to finish. Won't block view for more than this.


@mlb_dashboard.route('/players')
def index():
    msg = session.get('messages')
    session.clear()

    columns = Player.__table__.columns.keys()
    columns = ['id', 'mlbgame_id', 'full_name', 'last_name', 'fd_fpts_avg', 'fpts', 'dates']
    #special_columns = ['fpts']
    special_columns = []
    return render_template('mlb_dashboard.html',
            columns=columns,
            special_columns=special_columns)

def parse_datatable(playerType):

    if playerType == 'pitcher':
        sparklineClassName = 'inlinespark-pitchers'
        statlineColumn = 'pitcherstatlines'
    elif playerType == 'batter':
        sparklineClassName = 'inlinespark-batters'
        statlineColumnName = 'batterstatlines.fd_fpts'
        statlineColumn = 'batterstatlines'

    def spanned(l):
        result = ''.join(['<canvas class="chart">',
                         l,
                         '</canvas>'
                         ])
        return result
    def dated(l):
        return l


    # defining columns
    #columns = Player.__table__.columns.keys()
    #columns = lmap(lambda x: ColumnDT(x), columns)
    #special_columns = ['fpts']
    columns = []
    columns.append(ColumnDT('id'))
    columns.append(ColumnDT('mlbgame_id'))
    columns.append(ColumnDT('full_name'))
    columns.append(ColumnDT('last_name'))
    columns.append(ColumnDT(playerType+'_fd_fpts_avg', filter=lambda x: round(x, 1)))
    columns.append(ColumnDT(statlineColumn+'.fd_fpts'))
    columns.append(ColumnDT(statlineColumn+'.game.date', filter=dated))

    if playerType == 'batter':
        players = Player.query\
                    .join(BatterStatLine)\
                    .filter(Player.player_type == playerType)\
                    .group_by(Player.id)\
                    .having(func.count(Player.batterstatlines) > 0)
                    #having(func.length(users.c.name) > 4)
    else:
        players = Player.query\
                    .join(PitcherStatLine)\
                    .filter(Player.player_type == playerType)\
                    .group_by(Player.id)\
                    .having(func.count(Player.pitcherstatlines) > 0)

    rowTable = DataTables(request.args, Player, players, columns)

    # returns what is needed by DataTable
    return jsonify(rowTable.output_result())


@mlb_dashboard.route('/pitchers_table')
def pitchers_table():
    return parse_datatable('pitcher')
@mlb_dashboard.route('/batters_table')
def batters_table():
    return parse_datatable('batter')

@mlb_dashboard.route('/sync', methods=['POST'])
def sync():
    jsonData = request.json
    if not jsonData:
        return jsonify({'message': 'No input data provided',
                        'data':jsonData}), 400


    startDate = jsonData['startDate']
    endDate = jsonData['endDate']

    """Sync local database with data from MLBGAME """
    if redis.exists(POLL_SIMPLE_THROTTLE):
        return jsonify({'message': 'Already sycned once within the past 10 seconds. Not syncing until lock expires.',
                        'data':jsonData}), 400

    # Schedule the task.
    task = fetch_and_add_stat_lines_to_db.delay(startDate, endDate)  # Schedule the task to execute ASAP.
    session['messages'] = 'SHREK'

    # Attempt to obtain the results.
    for _ in range(int(WAIT_UP_TO / SLEEP_FOR)):
        time.sleep(SLEEP_FOR)
        if not task.ready():
            continue  # Task is still running.
        results = task.get(propagate=False)

        if isinstance(results, Exception):
            # The task crashed probably because of a bug in the code.
            if str(results) == 'Failed to acquire lock.':
                # Never mind, no bug. The task was probably running from Celery Beat when the user tried to run a second
                # instance of the same task.
                # Since the user is expecting this task to update the database, we'll tell them that results should be
                # updated within the minute, since the previously-running task should finish shortly.
                flash.info('Task scheduled, any new packages will appear within 1 minute.')
                #return redirect(url_for('.index'))
                return url_for('.index')
            raise results  # HTTP 500.

        if not results:
            flash.info('No new packages found.')
            #return redirect(url_for('.index'))
            return url_for('.index')

        if len(results) < 5:
            flash.info('New packages: {}'.format(', '.join(results)))
        else:
            flash.modal('New packages found:\n{}'.format(', '.join(results)))
        #return redirect(url_for('.index'))
        return url_for('.index')

    # If we get here, the timeout has expired and the task is still running.
    flash.info('Task scheduled, any new packages will appear within 15 minutes.')
    #return redirect(url_for('.index'))
    return url_for('.index')

@mlb_dashboard.route('/train')
def train():
    return render_template('mlb_train.html',
            predictors = enumerate(get_available_predictors()),
            transforms = enumerate(get_available_transforms()))

@mlb_dashboard.route('/player_names/')
def player_names():

    query = request.args.get('query')
    if not query:
        return jsonify({'message': 'No input data provided', 'data': {}}), 400
    players = Player.query\
                    .with_entities(Player.full_name, Player.player_type, Player.id)\
                    .filter(Player.full_name.like('%{}%'.format(query))).all()
    # For each player, return their startDate and endDate for their games.
    dates = lmap(get_player_career_start_end, players)

    playerNames = [{'value': playerTup[0], 'category': playerTup[1], 'id': playerTup[2], 'startDate': dateTup[0], 'endDate': dateTup[1]} for playerTup, dateTup in zip(players, dates)]
    #playerNames.append({'value': 'All', 'category': '-', 'id': -1, 'startDate': None, 'endDate': None})
    return jsonify(playerNames)

@mlb_dashboard.route('/predictor_names/')
def predictor_names():
    query = request.args.get('q')
    if not query:
        return jsonify({'message': 'No input data provided', 'data': {}}), 400

    predsJsons = dict(items=[{'id': i, 'text':v} for i,v in enumerate(preds)])
    return jsonify(predsJsons)



@mlb_dashboard.route('/fit', methods=['POST'])
def fit():
    formData = request.form
    if not formData:
        return jsonify({'message': 'No input data provided',
                        'data':formData }), 400


    """Sync local database with data from MLBGAME """
    if redis.exists(POLL_SIMPLE_THROTTLE):
        return jsonify({'message': 'Already sycned once within the past 10 seconds. Not syncing until lock expires.',
                        'data':formData}), 400

    #Clean up the formData.
    newFormData = parse_formdata(formData)
    # Schedule the task.
    task = fit_task.delay(newFormData)  # Schedule the task to execute ASAP.
    session['messages'] = 'SHREK'

    # Attempt to obtain the results.
    for _ in range(int(WAIT_UP_TO / SLEEP_FOR)):
        time.sleep(SLEEP_FOR)
        if not task.ready():
            continue  # Task is still running.
        results = task.get(propagate=False)

        if isinstance(results, Exception):
            # The task crashed probably because of a bug in the code.
            if str(results) == 'Failed to acquire lock.':
                # Never mind, no bug. The task was probably running from Celery Beat when the user tried to run a second
                # instance of the same task.
                # Since the user is expecting this task to update the database, we'll tell them that results should be
                # updated within the minute, since the previously-running task should finish shortly.
                flash.info('Task scheduled, any new packages will appear within 1 minute.')
                #return redirect(url_for('.index'))
                return url_for('.index')
            raise results  # HTTP 500.

        if not results:
            flash.info('No new packages found.')
            #return redirect(url_for('.index'))
            return url_for('.index')

        if len(results) < 5:
            flash.info('New packages: {}'.format(', '.join(results)))
        else:
            flash.modal('New packages found:\n{}'.format(', '.join(results)))
        #return redirect(url_for('.index'))
        return url_for('.index')

    # If we get here, the timeout has expired and the task is still running.
    #flash.info('Task scheduled, any new packages will appear within 15 minutes.')
    #return jsonify("hello")
    return hredirect(url_for('.train'), 'Training task scheduled.', typ='info')
    #return jsonify({'url':url_for('.index'), 'message:' 'Training task scheduled.')
    #return redirect(url_for('mlb.index'))


def get_player_career_start_end(playerTup):
    if playerTup[1] == 'batter':
        query = BatterStatLine.query\
                    .join(Game)\
                    .filter(BatterStatLine.player_id == playerTup[2])\
                    .order_by(Game.date).all()
    else:
        query = PitcherStatLine.query\
                    .join(Game)\
                    .filter(PitcherStatLine.player_id == playerTup[2])\
                    .order_by(Game.date).all()
    startDate = query[0].game.date
    endDate = query[-1].game.date
    startDateStr  = startDate.strftime('%d/%m/%Y')
    endDateStr  = endDate.strftime('%d/%m/%Y')
    return startDateStr, endDateStr

def parse_formdata(formData):
    newFormData = {}
    #Extract lists from formdata
    for key, value in formData.items():
        lst = formData.getlist(key)
        # If its a list, add it as a list
        if len(lst) >= 2:
            newFormData[key] = lst
        else:
            newFormData[key] = value
    newFormData['predictor_name'] = newFormData.pop('select_predictor')
    newFormData['data_transforms'] = newFormData.pop('select_datatransforms')
    newFormData['hypers'] = newFormData.pop('f_hypers')
    newFormData['data_cols'] = newFormData.pop('f_datacols')

    newFormData = parse_date_range(newFormData)
    newFormData['hypers'] = parse_yaml(newFormData['hypers'])
    newFormData['data_cols'] = parse_yaml(newFormData['data_cols'])
    newFormData['model'] = parse_modelData(newFormData)

    return newFormData

def parse_modelData(formData):
    modelData = {
            'hypers':formData.pop('hypers'),
            'data_cols':formData.pop('data_cols'),
            'predictor_name':formData.pop('predictor_name'),
            'start_date':formData.pop('start_date'),
            'end_date':formData.pop('end_date'),
            'data_transforms':formData.pop('data_transforms')}
    return modelData



def parse_yaml(yamlStr):
    parsedDict = toolz.pipe(yamlStr,
            lambda x: x.replace('\t','    '),
            lambda x: x.replace('\r',''),
            yaml.load)
    return parsedDict

def parse_date_range(formData):
    dates = formData['daterange'].split('-')
    startDate, endDate = lmap(parse_date, dates)
    formData['start_date'] = startDate
    formData['end_date'] = endDate
    del formData['daterange']
    return formData
