from marshmallow import Schema, fields, ValidationError, pre_load

from dfs_portal.config import HardCoded
from dfs_portal.utils import htools


# Custom validators
def must_not_be_blank(data):
    if not data:
        raise ValidationError('Data not provided.')


class StadiumSchema(Schema):
    id = fields.Int(dump_only=True)
    name = fields.Str()
    team = fields.Nested('TeamSchema', required=True, only=['name'])


class PlayerSchema(Schema):
    id = fields.Int(dump_only=True)
    mlbgame_id = fields.Int(required=True, validate=lambda x: x > 0)
    full_name = fields.Str(required=True, validate=must_not_be_blank)
    last_name = fields.Str(required=False, validate=must_not_be_blank)
    player_type = fields.Str(required=True, validate=lambda x: x in HardCoded.MLB_PlayerType)


class TeamSchema(Schema):
    id = fields.Int(dump_only=True)
    name = fields.Str(required=True)
    city = fields.Str(required=True)
    cityAbbr = fields.Str(required=True)
    players = fields.Nested(PlayerSchema, many=True, only=['full_name'])


class GameSchema(Schema):
    id = fields.Int(dump_only=True)
    mlbgame_id = fields.Str(required=True)
    date = fields.DateTime(required=True)
    home_team = fields.Nested(TeamSchema, validate=must_not_be_blank, only=['name'])
    away_team = fields.Nested(TeamSchema, validate=must_not_be_blank, only=['name'])
    stadium = fields.Nested(StadiumSchema, only=['name'])
    weather_pop = fields.Float(validate=lambda x: x >= 0 and x <= 1.0)
    weather_wind_speed = fields.Float(validate=lambda x: x >= 0)
    weather_relative_dir = fields.Float(validate=lambda x: x >= 0)
    weather_temp = fields.Float(validate=lambda x: x > -273)
    weather_humid = fields.Float(validate=lambda x: 0 <= x and x <= 100)


class BatterStatLineSchema(Schema):
    id = fields.Int(dump_only=True)
    player = fields.Nested(PlayerSchema, validate=must_not_be_blank, only=['full_name', 'id'])
    game = fields.Nested(GameSchema, validate=must_not_be_blank, only=['mlbgame_id', 'date'])

    avg = fields.Float(required=True, validate=lambda x: x >= 0)
    bb = fields.Int(required=True, validate=lambda x: x >= 0)
    twob = fields.Int(required=True, validate=lambda x: x >= 0)
    h = fields.Int(required=True, validate=lambda x: x >= 0)
    hbp = fields.Int(required=True, validate=lambda x: x >= 0)
    hr = fields.Int(required=True, validate=lambda x: x >= 0)
    r = fields.Int(required=True, validate=lambda x: x >= 0)
    rbi = fields.Int(required=True, validate=lambda x: x >= 0)
    sb = fields.Int(required=True, validate=lambda x: x >= 0)
    so = fields.Int(required=True, validate=lambda x: x >= 0)
    threeb = fields.Int(required=True, validate=lambda x: x >= 0)
    ab = fields.Int(required=True, validate=lambda x: x >= 0)
    fd_fpts = fields.Float(required=True)

    # comes from dsrc_rotoguru
    salary = fields.Int(validate=lambda x: x >= 0)


class PitcherStatLineSchema(Schema):
    id = fields.Int(dump_only=True)
    player = fields.Nested(PlayerSchema, validate=must_not_be_blank, only=['full_name', 'id'])
    game = fields.Nested(GameSchema, validate=must_not_be_blank, only=['mlbgame_id'])

    # (['era', 'win', 'er', 'so', 'out'])
    era = fields.Float(required=True, validate=lambda x: x >= 0)
    win = fields.Boolean(required=True)
    er = fields.Int(required=True, validate=lambda x: x >= 0)
    so = fields.Int(required=True, validate=lambda x: x >= 0)
    out = fields.Int(required=True, validate=lambda x: x >= 0)
    fd_fpts = fields.Float(required=True)

    # comes from dsrc_rotoguru
    salary = fields.Int(validate=lambda x: x >= 0)


class ModelSchema(Schema):
    player = fields.Nested(PlayerSchema, validate=must_not_be_blank, only=['full_name', 'id'])
    # hyper = fields.Nested(ModelHyperSchema, validate=must_not_be_blank, only=['id'])

    # hypers = fields.List(required =True, cls_or_instance=fields.List(cls_or_instance=fields.Str))
    # hypers = LDict(required=True)
    hypers = fields.Method('dictify', required=True, deserialize='listify')
    hypers_dict = fields.Method('dictify', deserialize='dictify', load_from='hypers')
    data_cols = fields.Method('dictify', required=True, deserialize='listify')
    data_cols_dict = fields.Method('dictify', deserialize='dictify', load_from='data_cols')
    predictor_name = fields.Str(required=True)
    start_date = fields.DateTime(required=True)
    end_date = fields.DateTime(required=True)
    data_transforms = fields.List(required=True, cls_or_instance=fields.Str)

    def listify(self, value):
        return htools.listify(value)

    def dictify(self, obj):
        return obj



class ModelFitSchema(Schema):
    model = fields.Nested('ModelSchema', required=True)
    player_id = fields.Int(required=True)
    player_type = fields.Str(required=True)

class ModelPredictSchema(Schema):
    pred = fields.Nested('PredSchema', required=True)
    player_id = fields.Int(required=True)
    player_type = fields.Str(required=True)
    pred_start_date = fields.DateTime(required=True)
    pred_end_date = fields.DateTime(required=True)





class PredSchema(Schema):
    model = fields.Nested(ModelSchema, validate=must_not_be_blank, only=['id'])
    start_date = fields.DateTime(required=True)
    end_date = fields.DateTime(required=True)
    pred_col = fields.List(cls_or_instance=fields.Float)






player_schema = PlayerSchema()
players_schema = PlayerSchema(many=True)
game_schema = GameSchema()
games_schema = GameSchema(many=True)
stadium_schema = StadiumSchema()
stadiums_schema = StadiumSchema(many=True)
team_schema = TeamSchema()
teams_schema = TeamSchema(many=True)
batter_stat_line_schema = BatterStatLineSchema()
batter_stat_lines_schema = BatterStatLineSchema(many=True)
pitcher_stat_line_schema = PitcherStatLineSchema()
pitcher_stat_lines_schema = PitcherStatLineSchema(many=True)
model_schema = ModelSchema()
model_fitting_function_schema = ModelFitSchema()
model_predict_function_schema = ModelPredictSchema()
pred_schema = PredSchema()
