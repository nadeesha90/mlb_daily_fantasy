import pudb
import pudb




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
