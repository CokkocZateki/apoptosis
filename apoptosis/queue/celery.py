from celery import Celery

celery_queue = Celery(
    "apoptosis",
    broker="redis://localhost",
    backend="redis://localhost"
)

if __name__ == "__main__":
    import apoptosis.queue.user
    import apoptosis.queue.group

    celery_queue.start()
