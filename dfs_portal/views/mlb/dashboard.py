import pudb
import time
import numpy as np
from dateutil.parser import parse as parse_date

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
from dfs_portal.utils.htools import lmap

SLEEP_FOR = 0.1  # Seconds to wait in between checks.
WAIT_UP_TO = 5  # Wait up to these many seconds for task to finish. Won't block view for more than this.


@mlb_dashboard.route('/players')
def index():
    msg = session.get('messages')
    session.clear()

    #pitchers = Player.query\
                #.order_by('full_name')\
                #.filter(Player.player_type == 'pitcher')\
                #.all()
    #for pitcher in pitchers:
        #statlines = PitcherStatLine.query\
                        #.join(Game)\
                        #.add_column(Game.date)\
                        #.filter(PitcherStatLine.player_id == pitcher.id)\
                        #.order_by('date')\
                        #.with_entities(PitcherStatLine.fd_fpts)\
                        #.all()
        #fpts = [t[0] for t in statlines]
        #fpts_str = str(fpts)[1:-1]
        #pitcher.fpts = fpts_str
#
    #statlines = map(lambda x: list(
    #players = Player.query.order_by('full_name').paginate(1, per_page=25, error_out=False)
    #pitchers = pitchers[:20]
    columns = Player.__table__.columns.keys()
    columns = ['id', 'mlbgame_id', 'full_name', 'last_name', 'fd_fpts_avg', 'fpts']
    #special_columns = ['fpts']
    special_columns = []
    return render_template('dashboard.html',
            columns=columns,
            special_columns=special_columns)
            #batters=batters,
            #pitchers=pitchers,
    #return render_template('dashboard.html')

def parse_datatable(playerType):

    if playerType == 'pitcher':
        sparklineClassName = 'inlinespark-pitchers'
        statlineColumn = 'pitcherstatlines'
    elif playerType == 'batter':
        sparklineClassName = 'inlinespark-batters'
        statlineColumnName = 'batterstatlines.fd_fpts'
        statlineColumn = 'batterstatlines'

    def spanned(l):
        result = ''.join(['<span class="{}">'.format(sparklineClassName),
                         l,
                         '</span>'
                         ])
        return result
    def rnd(num):
        pu.db

    # defining columns
    columns = Player.__table__.columns.keys()
    #columns = lmap(lambda x: ColumnDT(x), columns)
    special_columns = ['fpts']
    columns = []
    columns.append(ColumnDT('id'))
    columns.append(ColumnDT('mlbgame_id'))
    columns.append(ColumnDT('full_name'))
    columns.append(ColumnDT('last_name'))
    columns.append(ColumnDT(playerType+'_fd_fpts_avg', filter=lambda x: round(x, 1)))
    #columns.append(ColumnDT(statlineColumn+'.fd_fpts', filter=spanned))
    columns.append(ColumnDT(statlineColumn+'.fd_fpts'))
    #columns.append(ColumnDT(statlineColumnName, filter=avg))

    #subq = Player.query.with_entities(func.avg(BatterStatLine.fd_fpts).label('fptsavg'))\
               #.subquery()
    #players = Player.query\
                #.select_entity_from(subq)\
                #.options(subqueryload(statlineColumn))\
                #.add_column('fptsavg')\
                #.filter(Player.player_type == playerType)

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
                    #having(func.length(users.c.name) > 4)
                    #.filter(Player.player_type == playerType)
                    #.filter(Player.id == PitcherStatLine.player_id)
                    #.outerjoin(Player.pitcherstatlines)\
                    #.options(joinedload(Player.pitcherstatlines))\
                    #.options(joinedload(statlineColumn))\
                    #.options(contains_eager(Player.pitcherstatlines))
                    #.options(joinedload(statlineColumn))\
                    #.options(subqueryload(statlineColumn))\
                    #.join(PitcherStatLine, Player.id == PitcherStatLine.player_id)\
                    #.options(subqueryload(statlineColumn))\
    #players = Player.query\
                #.options(subqueryload(statlineColumn))\
                    #.subqueryload(statlineColumnName))\
                #.filter(Player.player_type == playerType)

                #.order_by('full_name')
                #.outerjoin(PitcherStatLine)
                #.filter(Player.player_type == 'pitcher')
    # instantiating a DataTable for the query and table needed
    #Rating.query.with_entities(func.avg(Rating.field2).label('average')).filter(Rating.url == url_string.netloc)
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
