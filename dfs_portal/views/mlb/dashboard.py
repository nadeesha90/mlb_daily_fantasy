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
from dfs_portal.models.redis import T_SYNC_PLAYERS
from dfs_portal.tasks.mlbgame import fetch_and_add_stat_lines_to_db
from dfs_portal.tasks.optimize import optimize_rosters_task
from dfs_portal.tasks.train import create_model_task, fit_player_task, fit_all_task
from dfs_portal.tasks.train import create_model_task, fit_player_task, fit_all_task, predict_player_task, predict_all_task
from dfs_portal.utils.htools import lmap, hredirect
from dfs_portal.utils.ctools import wait_for_task
from dfs_portal.core.abstract_predictor import get_available_predictors
from dfs_portal.core.transforms import get_available_transforms
SLEEP_FOR = 0.1  # Seconds to wait in between checks.
WAIT_UP_TO = 2  # Wait up to these many seconds for task to finish. Won't block view for more than this.


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
    if redis.exists(T_SYNC_PLAYERS):
        return jsonify({'message': 'Already sycned once within the past 10 seconds. Not syncing until lock expires.',
                        'data':jsonData}), 400

    # Schedule the task.
    task = fetch_and_add_stat_lines_to_db.delay(startDate, endDate)  # Schedule the task to execute ASAP.

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
    models = Model.query\
                    .with_entities(Model.nickname)\
                    .all()
    models = [ m[0] for m in models ]

    # List of valid training frequencies
    freqs = [1,7,14,30,-1]
    return render_template('mlb_train.html', models=models, freqs=freqs)

@mlb_dashboard.route('/predict')
def predict():
    models = Model.query\
                    .with_entities(Model.nickname)\
                    .all()
    models = [ m[0] for m in models ]

    # List of valid training frequencies
    freqs = [1,7,14,30,-1]
    return render_template('mlb_predict.html', models=models, freqs=freqs)


@mlb_dashboard.route('/model')
def model():
    return render_template('mlb_model.html',
            predictors = enumerate(get_available_predictors()),
            transforms = enumerate(get_available_transforms()))

@mlb_dashboard.route('/optimize')
def optimize():
    return render_template('mlb_optimize.html')



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

@mlb_dashboard.route('/model_nicknames/')
def model_nicknames():
    query = request.args.get('q')
    if not query:
        return jsonify({'message': 'No input data provided', 'data': {}}), 400
    models = Model.query\
                    .with_entities(Model.nickname)\
                    .all()

    modelNames = [{'value': modelTup[0]} for modelTup in models]
    return jsonify(modelNames )

@mlb_dashboard.route('/create_model', methods=['POST'])
def create_model():
    formData = request.form
    if not formData:
        return jsonify({'message': 'No input data provided',
                        'data':formData }), 400

    #Clean up the formData.
    newFormData = parse_model_formdata(formData)
    task = create_model_task.delay(newFormData)
    result = wait_for_task(task, 'create_model_task', 0.5, SLEEP_FOR)
    if result.status == 'none':
        return hredirect(url_for('.model'), 'Create model task scheduled', typ='info')
    elif result.status == 'success':
        return hredirect(url_for('.model'), 'Create model task finished'.format(result.msg), typ='info')
    else:
        if result:
            message = result.msg
        else:
            message = ''
        return hredirect(url_for('.model'), 'Error: {}'.format(message), typ='danger')

@mlb_dashboard.route('/fit', methods=['POST'])
def fit():
    formData = request.form
    if not formData:
        return jsonify({'message': 'No input data provided',
                        'data':formData }), 400

    #Clean up the formData.
    newFormData = parse_player_formdata(formData)
    # Schedule the tasks
    if newFormData['train_select'] == 'all':
        task = fit_all_task.delay(newFormData)
        results = wait_for_task(task, 'fit_all_task', WAIT_UP_TO, SLEEP_FOR)
        failResults = filter(lambda t: t.status != 'success', results)
        if not failResults:
            return hredirect(url_for('.train'), 'Training all players scheduled.', typ='info')
        else:
            return hredirect(url_for('.train'), 'Training all players failed.', typ='danger')
    else:
        task = fit_player_task.delay(newFormData)
        result = wait_for_task(task, 'fit_player_task', WAIT_UP_TO, SLEEP_FOR)
        if result.status == 'none':
            return hredirect(url_for('.train'), 'Training player task scheduled', typ='info')
        elif result.status == 'success':
            return hredirect(url_for('.train'), 'Training player task finished'.format(result.msg), typ='info')
        else:
            if result:
                message = result.msg
            else:
                message = ''
            return hredirect(url_for('.train'), 'Error: {}'.format(message), typ='danger')

@mlb_dashboard.route('/predict_task', methods=['POST'])
def predict_task():
    formData = request.form
    if not formData:
        return jsonify({'message': 'No input data provided',
                        'data':formData }), 400

    #Clean up the formData.
    newFormData = parse_player_formdata(formData)
    # Schedule the tasks
    if newFormData['predict_select'] == 'all':
        task = predict_all_task.delay(newFormData)
        results = wait_for_task(task, 'predict_all_task', WAIT_UP_TO, SLEEP_FOR)
        failResults = filter(lambda t: t.status != 'success', results)
        if not failResults:
            return hredirect(url_for('.train'), 'Training all players scheduled.', typ='info')
        else:
            return hredirect(url_for('.train'), 'Training all players failed.', typ='danger')
    else:
        task = predict_player_task.delay(newFormData)
        result = wait_for_task(task, 'predict_all_task', WAIT_UP_TO, SLEEP_FOR)
        if result.status == 'none':
            return hredirect(url_for('.train'), 'Training player task scheduled', typ='info')
        elif result.status == 'success':
            return hredirect(url_for('.train'), 'Training player task finished'.format(result.msg), typ='info')
        else:
            if result:
                message = result.msg
            else:
                message = ''
            return hredirect(url_for('.train'), 'Error: {}'.format(message), typ='danger')

@mlb_dashboard.route('/optimize_task', methods=['POST'])
def optimize_task():
    formData = request.form
    if not formData:
        return jsonify({'message': 'No input data provided',
                        'data':formData }), 400

    #Clean up the formData.
    newFormData = parse_optimize_formdata(formData)
    # Schedule the tasks
    task = optimize_rosters_task.delay(newFormData)
    result = wait_for_task(task, 'optimize_rosters_task', WAIT_UP_TO, SLEEP_FOR)
    if result.status == 'none':
        return hredirect(url_for('.train'), 'Training player task scheduled', typ='info')
    elif result.status == 'success':
        return hredirect(url_for('.train'), 'Training player task finished'.format(result.msg), typ='info')
    else:
        if result:
            message = result.msg
        else:
            message = ''
        return hredirect(url_for('.train'), 'Error: {}'.format(message), typ='danger')



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

def parse_player_formdata(formData):
    newFormData = {}
    #Extract lists from formdata
    for key, value in formData.items():
        lst = formData.getlist(key)
        # If its a list, add it as a list
        if len(lst) >= 2:
            newFormData[key] = lst
        else:
            newFormData[key] = value
    newFormData['frequency'] = int(newFormData['frequency'])
    newFormData = parse_date_range(newFormData)

    return newFormData

def parse_model_formdata(formData):
    newFormData = {}
    #Extract lists from formdata
    for key, value in formData.items():
        lst = formData.getlist(key)
        # If its a list, add it as a list
        if len(lst) >= 2:
            newFormData[key] = lst
        else:
            newFormData[key] = value
    modelData = {
        'predictor_name': newFormData['predictor_name'],
        'hypers': parse_yaml(newFormData['hypers']),
        'data_cols': parse_yaml(newFormData['data_cols']),
    }
    return modelData

def parse_optimize_formdata(formData):
    newFormData = {}
    #Extract lists from formdata
    for key, value in formData.items():
        lst = formData.getlist(key)
        # If its a list, add it as a list
        if len(lst) >= 2:
            newFormData[key] = lst
        else:
            newFormData[key] = value
    newFormData = parse_date_range(newFormData)
    newFormData['optimize_params'] = parse_yaml(newFormData['optimize_params']),
    return newFormData


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
