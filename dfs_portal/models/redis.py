"""Redis keys used throughout the entire application (Flask, etc.)."""

# Lock
T_SYNC_PLAYERS = 'dfs_portal:t_sync_players'


T_CREATE_MODEL = 'dfs_portal:t_create_model' # Lock.

T_FIT_ALL = 'dfs_portal:t_fit_all'  # Lock.
T_FIT_ID = 'dfs_portal:t_fit_id_{}'

T_PREDICT_ALL = 'dfs_portal:t_predict_all'  # Lock.
T_PREDICT_ID = 'dfs_portal:t_predict_id_{}'



# Progress
FIT_ALL_TOTAL_PROGRESS = 'dfs_portal:fit_all_total_progress'  
FIT_ALL_CURRENT_PROGRESS = 'dfs_portal:fit_all_current_progress'


FIT_PLAYER_TOTAL_PROGRESS = 'dfs_portal:fit_player_total_progress'  
FIT_PLAYER_CURRENT_PROGRESS = 'dfs_portal:fit_player_current_progress' 
