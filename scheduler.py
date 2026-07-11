"""獨立排程服務進入點。

web app 的 gunicorn worker 全部關閉排程（PREMIUM_WEEKLY_SCHEDULER_ENABLED=0），
改由這個單一容器跑 premium 週賽排程，避免多 worker 各跑一次。
不需要 gevent / message_queue：純背景 hourly 工作。
"""
import time
import app

if __name__ == '__main__':
    print('[scheduler] starting standalone premium weekly scheduler...', flush=True)
    app.init_db()
    app._start_premium_weekly_scheduler()
    print('[scheduler] premium weekly scheduler thread started; idling.', flush=True)
    while True:
        time.sleep(3600)
