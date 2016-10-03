import pudb
import time
from dateutil.parser import parse as parse_date

from flask import redirect, render_template, url_for, request, jsonify, session

from dfs_portal.blueprints import mlb_dashboard
from dfs_portal.core import flash
from dfs_portal.extensions import redis
from dfs_portal.models.mlb import *
from dfs_portal.models.redis import POLL_SIMPLE_THROTTLE
from dfs_portal.tasks.mlbgame import fetch_and_add_stat_lines_to_db

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
    special_columns = ['fpts']
    return render_template('dashboard.html',
            columns=columns,
            special_columns=special_columns)
            #batters=batters,
            #pitchers=pitchers,
    #return render_template('dashboard.html')

@mlb_dashboard.route('/pitchers_ajax')
def pitchers_table(request):
    # defining columns
    columns = []
    columns.append(ColumnDT('id'))
    columns.append(ColumnDT('name', filter=_upper))
    columns.append(ColumnDT('address.description')) # where address is an SQLAlchemy Relation
    columns.append(ColumnDT('created_at', filter=str))


    # instantiating a DataTable for the query and table needed
    rowTable = DataTables(request.GET, User, query, columns)

    # returns what is needed by DataTable
    return rowTable.output_result()

@mlb_dashboard.route('/batters_ajax')
def batters_table(request):
    # defining columns
    columns = Player.__table__.columns.keys()
    special_columns = ['fpts']
    columns = []
    columns.append(ColumnDT('id'))
    columns.append(ColumnDT('name', filter=_upper))
    columns.append(ColumnDT('address.description')) # where address is an SQLAlchemy Relation
    columns.append(ColumnDT('created_at', filter=str))

    batters = Player.query\
                .order_by('full_name')\
                .filter(Player.player_type == 'batter')\
                .all()
    for batter in batters:
        statlines = BatterStatLine.query\
                        .join(Game)\
                        .add_column(Game.date)\
                        .filter(BatterStatLine.player_id == batter.id)\
                        .order_by('date')\
                        .with_entities(BatterStatLine.fd_fpts)\
                        .all()
        fpts = [t[0] for t in statlines]
        fpts_str = str(fpts)[1:-1]
        batter.fpts = fpts_str

    batters = batters[:20]

    # instantiating a DataTable for the query and table needed
    rowTable = DataTables(request.GET, User, query, columns)

    # returns what is needed by DataTable
    return rowTable.output_result()


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
