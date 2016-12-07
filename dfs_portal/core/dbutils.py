import pudb
import time
import datetime



from dfs_portal.models.mlb import PlayerModel, Model, Player, BatterStatLine, PitcherStatLine, Game, Pred




def reset_to_start_of_week(date):
    day_of_week = date.weekday()
    beginning_of_week = date - datetime.timedelta(day_of_week)
    return beginning_of_week


def retrain_start_end_cycles(careerStartDate, careerEndDate, period=7):
    startDates = []
    endDates = []
    careerStartDate = reset_to_start_of_week(careerStartDate)
    careerEndDate = reset_to_start_of_week(careerEndDate)
    number_of_periods = (careerEndDate.date() - careerStartDate.date()).days / period
    assert(number_of_periods == int(number_of_periods))
    number_of_periods = int(number_of_periods)
    endDates = [ careerStartDate + datetime.timedelta(period) * (i+1) for i in range(number_of_periods) ]
    endDates[-1] = careerEndDate
    # TODO: endDates cycle has bias, i.e., if start=sep1 2pm, end=sep22 9pm
    # then endDates = [ sep1 2pm, sep8 2pm, sep15 2pm sep22 9pm ]
    return endDates

def get_player_career_start_end(playerType, playerId):
    #playerType, playerId = playerTup
    if playerType == 'batter':
        query = BatterStatLine.query\
                    .join(Game)\
                    .filter(BatterStatLine.player_id == playerId)\
                    .order_by(Game.date).all()
    else:
        query = PitcherStatLine.query\
                    .join(Game)\
                    .filter(PitcherStatLine.player_id == playerId)\
                    .order_by(Game.date).all()
    startDate = query[0].game.date
    endDate = query[-1].game.date
    #startDateStr  = startDate.strftime('%d/%m/%Y')
    #endDateStr  = endDate.strftime('%d/%m/%Y')
    return startDate, endDate


def query_player_stat_line(playerTup):
    #playerTup = (playerId, playerType, startDate, endDate)
    playerId, playerType, startDate, endDate = playerTup 
    if playerType == 'batter':
        query = BatterStatLine.query\
                .join(Game)\
                .filter(BatterStatLine.player_id == playerId)\
                .filter(
                        Game.date >= startDate,
                        Game.date < endDate)
    else:
        query = PitcherStatLine.query\
                .join(Game)\
                .filter(PitcherStatLine.player_id == playerId)\
                .filter(
                        Game.date >= startDate,
                        Game.date < endDate)
    return query





#if __name__ == "__main__":
#    start = datetime.date(2016, 1, 1)
#    end = datetime.date.today()
#    retrain_start_end_cycles(start, end)
