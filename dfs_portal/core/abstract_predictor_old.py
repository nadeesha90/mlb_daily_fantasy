import sys
from os.path import dirname, realpath
root = dirname(dirname(realpath(__file__)))
sys.path.append(root)

# Python core modules
import importlib
import os
import inspect
from pprint import pprint
from ast import literal_eval
from collections import OrderedDict

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

class AbstractPredictor (object):
    def __init__(self, db):
        self.dbroot = db
    def __del__(self):
        pass

    def fit(self, predictorParams):
        hypers, errors = self._validate_predictor_params(predictorParams)
        if errors:
            payload = self._get_payload("Error with input arguments!", errors)
        else:
            predictorName = predictorParams.get('name')
            dataFilePath = predictorParams.get('data_file_path')
            features = eval(predictorParams.get('features'))
            targetCol = predictorParams.get('target_col')

            #assert predictorName, 'Must specify name for predictor'
            #print (content)

            # Check if pObj exists in ZODB

            forceOverwrite = json.loads(predictorParams.get('force').lower())

            # Drop force from the predictor params
            if 'force' in predictorParams:
                del predictorParams['force']
            if 'test_x' in predictorParams:
                del predictorParams['test_x']
            pObjKey = tuplify(predictorParams)
            #pprint (pObjKey)
            if pObjKey in self.dbroot and not forceOverwrite:
                pObj = self.dbroot[pObjKey]
                result = not pObj.skipFit
            else:
                pObj = self._get_concrete_predictor_obj (predictorName,
                                                dataFilePath,
                                                hypers,
                                                targetCol,
                                                features)
                pObj.fit()
                self.dbroot[pObjKey] = pObj
                result = not pObj.skipFit

            pObj._p_changed = 1
            transaction.commit()
            if result:
                params = pObj.get_params()
                payload = self._get_payload("Fit complete!", params)
            else:
                payload = self._get_payload("Fit fail!")

        return payload
    def score(self, predictorParams):
        userXTest = predictorParams.get('test_x')
        forceOverwrite = json.loads(predictorParams.get('force').lower())

        # Drop force from the predictor params
        if 'force' in predictorParams:
            del predictorParams['force']
        if 'test_x' in predictorParams:
            del predictorParams['test_x']
        pObjKey = tuplify(predictorParams)

        # Check if pObj exists in ZODB
        if pObjKey in self.dbroot:
            #print ("Using existing object...")
            pObj = self.dbroot[pObjKey]
            #score = pObj.calc_score(userXTest = userXTest)
            if forceOverwrite:
                pObj.modelScore = None
            score = pObj.score(userXTest = userXTest)
            payload = self._get_payload("Score", score)
        else:
            #raise Exception("Run fit first!")
            payload = self._get_payload("No object found with given params. Run fit first!", predictorParams)
        return payload
    def predict(self, predictorParams):
        userXTest = predictorParams.get('test_x')
        date = predictorParams.get('date')

        # Drop force from the predictor params
        if 'force' in predictorParams:
            del predictorParams['force']
        # Drop test_x from params. Don't need to key-ify it
        if 'test_x' in predictorParams:
            del predictorParams['test_x']
        if 'date' in predictorParams:
            del predictorParams['date']
        pObjKey = tuplify(predictorParams)
        #pprint (pObjKey)
        # Check if pObj exists in ZODB
        if pObjKey in self.dbroot:
            #print ("Using existing object...")
            pObj = self.dbroot[pObjKey]
            prediction = pObj.predict(userXTest)
            payload = self._get_payload("Predicted", prediction)
        else:
            #raise Exception("Run fit first!")
            payload = self._get_payload("No object found with given params. Run fit first!", predictorParams)
        return payload

    def _get_concrete_predictor_obj (self, predictorName, dataFilePath, hypers, targetCol, features):
        if not predictorName :
                predictorName = 'base'

        moduleName = '%s_predictor' % predictorName.lower()
        className = '%sPredictor' % predictorName.capitalize()
        module = importlib.import_module('nba.predictors.%s' % moduleName)
        predictorClass = getattr(module, '%s' % className )
        pObj = predictorClass (dataFilePath, hypers, targetCol, features)
        return pObj

    def _get_predictor_schema (self):
        schema = Schema ({
            'name': All (str, Length (min=1)),
            'data_file_path': IsFile(),
            }, default_keys=Required, extra_keys=Allow)
        return schema


    def _validate_predictor_params (self, params):
        errors = None
        schema = self._get_predictor_schema()
        try:
            schema (params)
        except (Invalid, MultipleInvalid) as exc:
            errors = exc
            print ("Error validing predictor params: %s" % exc)
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
    dbPath = os.path.join(currentDir, 'db', 'app.fs')
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

    @app.route ('/fit')
    def fit():
        #content = request.get_json(silent=True)
        args = request.args
        predictorParams = OrderedDict(sorted(args.items()))
        payload = p.fit(predictorParams)
        return payload

    @app.route ('/score')
    def score():
        args = request.args
        predictorParams = OrderedDict(sorted(args.items()))
        payload = p.score(predictorParams)
        return payload
    @app.route ('/predict')
    def predict():
        args = request.args
        predictorParams = OrderedDict(sorted(args.items()))
        payload = p.predict(predictorParams)
        return payload



    return app, db

def setup_helper_class (db):
    #global db
    #global app
    #app = create_app()
    p = AbstractPredictor(db)
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
