import sys
from os.path import dirname, realpath
root = dirname(dirname(realpath(__file__)))
sys.path.append(root)

# Python core modules
import importlib
import os
import inspect
from ast import literal_eval
from collections import OrderedDict
import pprint

#Pypi modules
import json
from flask import Flask, request, jsonify
#from flask.ext.classy import FlaskView, route
from contracts import contract, new_contract
import pudb
#from voluptuous import Schema, All, Length, MultipleInvalid, ALLOW_EXTRA
from good import Schema, All, Length, Invalid, MultipleInvalid, Allow, Required, IsFile
from toolz import map, keyfilter, keymap, valmap
from toolz.functoolz import pipe
#Custom modules
#from . import w5_zodb.W5ZODB as W5ZODB
#import w5_zodb as z
from flask.ext.zodb import ZODB, transaction
from nba.utils.htools import tuplify

currentDir = dirname(os.path.realpath(__file__))

class AbstractOptimizer (object):
    def __init__(self, db):
        self.dbroot = db
    def __del__(self):
        pass

    def optimize(self, optimizerParams):
        hypers, errors = self._validate_optimizer_params(optimizerParams)
        if errors:
            payload = self._get_payload("Error with input arguments!", errors)
        else:
            optimizerName = optimizerParams.get('name')
            date = optimizerParams.get('date')
            pisFilePath = optimizerParams.get('pis_file_path')
            salaryFilePath = optimizerParams.get('salary_file_path')
            pisFilePath2 = optimizerParams.get('pis_file_path2')
            salaryFilePath2 = optimizerParams.get('salary_file_path2')

            # Check if pObj exists in ZODB
            forceOverwrite = json.loads(optimizerParams.get('force').lower())
            # Drop force from the optimizer params
            if 'force' in optimizerParams:
                del optimizerParams['force']

            #pprint.pprint (optimizerParams)
            pObjKey = tuplify(optimizerParams)
            if pObjKey in self.dbroot and not forceOverwrite:
                pObj = self.dbroot[pObjKey]
                if pObj.solutions:
                    result = 'opt_success'
                else:
                    result = 'Re-run optimize!'
            else:
                pObj = self._get_concrete_optimizer_obj (optimizerName, hypers)
                if pisFilePath2:
                    result = pObj.optimize(date, pisFilePath, salaryFilePath, pisFilePath2=pisFilePath2, salaryFilePath2=salaryFilePath2)
                else:
                    result = pObj.optimize(date, pisFilePath, salaryFilePath)
                self.dbroot[pObjKey] = pObj
                pObj._p_changed = 1
                transaction.commit()
            payload = self._get_payload("Optimizer", result)

        return payload
    def get_rosters(self, optimizerParams):

        #print (optimizerParams)
        optimizerName = optimizerParams.get('name')
        date = optimizerParams.get('date')

        # Drop force from the optimizer params
        if 'force' in optimizerParams:
            del optimizerParams['force']
        #pprint.pprint (optimizerParams)
        pObjKey = tuplify(optimizerParams)
        # Check if pObj exists in ZODB
        if pObjKey in self.dbroot:
            #print ("Using existing object...")
            pObj = self.dbroot[pObjKey]
            rosters = pObj.get_rosters(date)
            payload = self._get_payload("Rosters", rosters)
        else:
            #raise Exception("Run fit first!")
            payload = self._get_payload("No object found with given params. Run optimize first!", optimizerParams)
        return payload
    def get_detailed_rosters(self, optimizerParams):

        #print (optimizerParams)
        optimizerName = optimizerParams.get('name')
        date = optimizerParams.get('date')

        # Drop force from the optimizer params
        if 'force' in optimizerParams:
            del optimizerParams['force']
        #pprint.pprint (optimizerParams)
        pObjKey = tuplify(optimizerParams)
        # Check if pObj exists in ZODB
        if pObjKey in self.dbroot:
            #print ("Using existing object...")
            pObj = self.dbroot[pObjKey]
            rosters = pObj.get_detailed_rosters(date)
            payload = self._get_payload("Rosters", rosters)
        else:
            #raise Exception("Run fit first!")
            payload = self._get_payload("No object found with given params. Run optimize first!", optimizerParams)
        return payload
    def get_amount_of_players(self, optimizerParams):
        hypers, errors = self._validate_optimizer_params(optimizerParams)
        if errors:
            payload = self._get_payload("Error with input arguments!", errors)
        else:
            optimizerName = optimizerParams.get('name')
            date = optimizerParams.get('date')
            pisFilePath = optimizerParams.get('pis_file_path')
            salaryFilePath = optimizerParams.get('salary_file_path')
            pisFilePath2 = optimizerParams.get('pis_file_path2')
            salaryFilePath2 = optimizerParams.get('salary_file_path2')

            # Check if pObj exists in ZODB
            forceOverwrite = json.loads(optimizerParams.get('force').lower())
            # Drop force from the optimizer params
            if 'force' in optimizerParams:
                del optimizerParams['force']

            #pprint.pprint (optimizerParams)
            pObj = self._get_concrete_optimizer_obj (optimizerName, hypers)
            result = pObj.get_amount_of_players(date, pisFilePath, salaryFilePath, pisFilePath2=pisFilePath2, salaryFilePath2=salaryFilePath2)
            pObj._p_changed = 1
            transaction.commit()
            payload = self._get_payload("Optimizer", result)

        return payload

    def _get_concrete_optimizer_obj (self, optimizerName, hypers):

        moduleName = '%s_optimizer' % optimizerName.lower()
        className = '%soptimizer' % optimizerName.capitalize()
        module = importlib.import_module('nba.optimizers.%s' % moduleName)
        optimizerClass = getattr(module, '%s' % className )
        pObj = optimizerClass (hypers)
        return pObj

    def _get_optimizer_schema (self):
        schema = Schema ({
            'name': All (str, Length (min=1)),
            'date': All (str, Length (min=1)),
            'pis_file_path': IsFile(),
            'salary_file_path': IsFile(),
            }, default_keys=Required, extra_keys=Allow)
        return schema
    def _validate_optimizer_params (self, params):
        errors = None
        schema = self._get_optimizer_schema()
        try:
            schema (params)
        except (Invalid, MultipleInvalid) as exc:
            errors = exc
            print ("Error validing optimizer params: %s" % exc)
        # Filter all hyper params that don't start with '_'
        hypers = pipe (
                    params,
                    self._keep_hyper_params,
                    self._coerce_hypers
                    )
        return hypers, errors

    def _coerce_hypers (self, hypers):
        def _safecast (a):
            try:
                return literal_eval(a)
            except (ValueError, SyntaxError):
                return a
        coercedHypers = valmap(_safecast, hypers)
        return coercedHypers


    def _keep_hyper_params (self, params):
        hypers = keyfilter (lambda x: x[0] == '_' , params)
        hypers = keymap (lambda x: x[1:], hypers)
        return hypers

    def _get_payload(self, msg, *args):
        payload = {'msg':msg}
        payload['data'] = list(args)
        payload = jsonify (payload)
        return payload

def create_db (app):
    db = ZODB(app)
    return db

def create_app(config_obj=None):
    app = Flask(__name__)
    app.debug = True
    dbPath = os.path.join(currentDir, 'db', 'opt.fs')
    dbUri = 'file://{}'.format(dbPath)
    app.config['ZODB_STORAGE'] = dbUri
    db = create_db (app)
    p = setup_helper_class(db)

    @app.route('/', methods=['GET', 'POST'])
    def index():
        return jsonify({
                "data":"In /",
                "success": True}
                )

    @app.route ('/optimize')
    def optimize():
        #content = request.get_json(silent=True)
        args = request.args
        optimizerParams = OrderedDict(sorted(args.items()))
        payload = p.optimize(optimizerParams)
        return payload

    @app.route ('/rosters')
    def get_rosters():
        args = request.args
        optimizerParams = OrderedDict(sorted(args.items()))
        payload = p.get_rosters(optimizerParams)
        return payload
    @app.route ('/det_rosters')
    def get_detailed_rosters():
        args = request.args
        optimizerParams = OrderedDict(sorted(args.items()))
        payload = p.get_detailed_rosters(optimizerParams)
        return payload
    @app.route ('/amt_players')
    def get_amount_of_players():
        args = request.args
        optimizerParams = OrderedDict(sorted(args.items()))
        payload = p.get_amount_of_players(optimizerParams)
        return payload

    return app, db

def setup_helper_class (db):
    #global db
    #global app
    #app = create_app()
    p = AbstractOptimizer(db)
    return p


app, db = create_app()

if __name__ == '__main__':
    #main('/')
    try:
        #app.debug = True
        #app.run()
        #app.run(host='localhost', port=8000)
        #app = create_app()
        app.run(host='localhost', port=8000)
    finally:
        db.close()
        # your "destruction" code
        pass
