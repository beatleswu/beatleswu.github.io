"""Standalone scheduler entrypoint.

The web app's gunicorn workers should keep scheduler flags disabled. This
process starts only the approved background scheduler threads in one place:
premium weekly and community leaderboard weekly.
"""

import time

import app


if __name__ == '__main__':
    print('[scheduler] starting standalone premium/community schedulers...', flush=True)
    app.init_db()
    app._start_premium_weekly_scheduler()
    app._start_community_leaderboard_weekly_scheduler()
    print('[scheduler] scheduler threads started; idling.', flush=True)
    while True:
        time.sleep(3600)
