from celery import Celery

import apoptosis.queue.user

celery_queue = Celery(
    "apoptosis",
    broker="redis://localhost",
    backend="redis://localhost"
)

if __name__ == "__main__":
    celery_queue.start()
