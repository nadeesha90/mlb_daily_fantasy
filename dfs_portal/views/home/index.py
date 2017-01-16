import pudb
from toolz import partial
from celery.task.control import  inspect
from flask import render_template, request, jsonify

from datatables import ColumnDT, DataTables
from dfs_portal.blueprints import home_index
from dfs_portal.tasks.test import long_task
from dfs_portal.tasks.mlbgame import fetch_and_add_stat_lines_to_db
from dfs_portal.schema.core import celery_result_schema
from dfs_portal.models.core import CeleryResult


from celery.backends.database.models import *
from celery.backends.database import session
@home_index.route('/')
def index():
    return render_template('home_index.html')

@home_index.route('task_table')
def task_table():
    result = parse_datatable()
    return result

def parse_datatable():

    # defining columns
    def get_key(key, r):
        result = '-'
        if isinstance(r, CeleryResult):
            val = getattr(r, key)
            if val:
                result = val
        return result

    columns = []
    columns.append(ColumnDT('result', filter=partial(get_key, 'name')))
    columns.append(ColumnDT('task_id'))
    columns.append(ColumnDT('status'))
    columns.append(ColumnDT('result', filter=partial(get_key, 'msg')))
    #columns.append(ColumnDT(playerType+'_fd_fpts_avg', filter=lambda x: round(x, 1)))
    #columns.append(ColumnDT(statlineColumn+'.fd_fpts'))
    #columns.append(ColumnDT(statlineColumn+'.game.date', filter=dated))

    sesh = session.SessionManager().session_factory('sqlite:///celery_results.db')
    allTasks = sesh.query(Task)

    rowTable = DataTables(request.args, Task, allTasks, columns)
    # returns what is needed by DataTable

    return jsonify(rowTable.output_result())


@home_index.route('task_progress')
def task_progress():
    sesh = session.SessionManager().session_factory('sqlite:///celery_results.db')
    runningTasks = sesh.query(Task).filter(Task.status == 'PROGRESS').all()

    # Create list of dictionaries with task info:
    # [{name: task_name, current: current_progress, total: total_progress}, ...]
    tasksProgress = []
    for task in runningTasks:
        tasksProgress.append(dict(
            name=task.result.name,
            current=task.result.currentProgress,
            total=task.result.totalProgress))
    return jsonify(tasksProgress)


