import pudb
from marshmallow import Schema, fields, ValidationError, pre_load, validates_schema, post_load
from marshmallow.validate import OneOf

from dfs_portal.models.core import CeleryResult

cStatus = ['fail', 'locked', 'success', 'none']

class CeleryResultSchema(Schema):
    currentProgress = fields.Integer(required=True)
    totalProgress = fields.Integer(required=True)
    data = fields.Method('data', deserialize='load_data', allow_none=True)
    #data = fields.Method('data')
    msg = fields.Str(allow_none=True)
    name = fields.Str(required=True)
    status = fields.Str(required=True, validate=OneOf(cStatus))

    def load_data(self, data):
        return data

    @validates_schema
    def validate_progress(self, obj):
        if obj['currentProgress'] > obj['totalProgress']:
            raise ValidationError('Current Progress must be less than Total Progress!')

    @pre_load
    def convert_exception(self, obj):
        #if data.get('exc_type'):
        #if data.get('exc_message'):
            #data['message'] = data['message'] + data.get('exc_message')
        return obj
    @post_load
    def make_obj(self, obj):
        return CeleryResult(**obj)

celery_result_schema = CeleryResultSchema()
