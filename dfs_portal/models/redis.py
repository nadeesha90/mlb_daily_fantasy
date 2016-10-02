"""Redis keys used throughout the entire application (Flask, etc.)."""

# Email throttling.
EMAIL_THROTTLE = 'dfs_portal:email_throttle:{md5}'  # Lock.

# PyPI throttling.
POLL_SIMPLE_THROTTLE = 'dfs_portal:poll_simple_throttle'  # Lock.

# PyPI throttling.
TOTAL_PROGRESS = 'dfs_portal:total'  # Lock.
CURRENT_PROGRESS = 'dfs_portal:current'  # Lock.
