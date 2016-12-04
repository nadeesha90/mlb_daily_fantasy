import pudb
import time
import datetime
import pudb




def reset_to_start_of_week(date):
    day_of_week = date.weekday()
    beginning_of_week = date - datetime.timedelta(day_of_week)
    return beginning_of_week


def retrain_start_end_cycles(careerStartDate, careerEndDate, period=7):
    startDates = []
    endDates = []
    careerStartDate = reset_to_start_of_week(careerStartDate)
    careerEndDate = reset_to_start_of_week(careerEndDate)
    number_of_periods = (careerEndDate - careerStartDate).days / period
    assert(number_of_periods == int(number_of_periods))
    number_of_periods = int(number_of_periods)
    endDates = [ careerStartDate + datetime.timedelta(period) * (i+1) for i in range(number_of_periods) ]
    return endDates




def get_player_career_start_end(allStatLines):
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
    startDate = allStatLines[0].game.date
    endDate = allStatLines[-1].game.date
    startDateStr  = startDate.strftime('%d/%m/%Y')
    endDateStr  = endDate.strftime('%d/%m/%Y')
    return startDateStr, endDateStr


if __name__ == "__main__":
    start = datetime.date(2016, 1, 1)
    end = datetime.date.today()
    retrain_start_end_cycles(start, end)
